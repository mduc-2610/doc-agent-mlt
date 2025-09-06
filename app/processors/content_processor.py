import os
import traceback
import re
import asyncio
import io
from typing import Optional, Tuple
from io import BytesIO
from fastapi import HTTPException, UploadFile
from llama_cloud_services import LlamaParse
from PIL import Image
import pytesseract
from bs4 import BeautifulSoup
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import torch
import librosa
from youtube_transcript_api import YouTubeTranscriptApi
import httpx
from app.config import settings
from app.storages import get_storage_provider

class WhisperModel:
    def __init__(self):
        self.processor = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
    
    def load_model(self):
        if self.processor is None:
            self.processor = WhisperProcessor.from_pretrained(settings.audio.model_name)
            self.model = WhisperForConditionalGeneration.from_pretrained(settings.audio.model_name)
            self.model.to(self.device)
    
    def _process_audio_chunk(self, chunk: torch.Tensor, chunk_idx: int) -> str:
        try:
            inputs = self.processor(chunk.numpy(), sampling_rate=settings.audio.sample_rate, return_tensors="pt")
            input_features = inputs.input_features.to(self.device)
            
            with torch.no_grad():
                predicted_ids = self.model.generate(
                    input_features,
                    max_length=settings.audio.max_tokens,
                    num_beams=settings.audio.num_beams,
                    early_stopping=True
                )
            
            transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)
            result = transcription[0].strip() if transcription else ""
            
            if result:
                print(f"Chunk {chunk_idx + 1} transcription: {result}")
            
            return result
        except Exception as e:
            print(f"Error processing chunk {chunk_idx + 1}: {e}")
            return ""
    
    async def transcribe_audio(self, audio_url: str) -> str:
        self.load_model()
        
        print(f"Processing audio file: {audio_url}")
        
        try:
            async with httpx.AsyncClient(timeout=settings.content.request_timeout) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                audio_array, _ = librosa.load(io.BytesIO(response.content), sr=settings.audio.sample_rate)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load audio file: {str(e)}")
        
        if len(audio_array) == 0:
            return "No audio detected in the file."
        
        print(f"Audio loaded: {len(audio_array)} samples, {len(audio_array)/settings.audio.sample_rate:.2f} seconds")
        
        chunk_length = settings.audio.chunk_duration * settings.audio.sample_rate
        min_length = int(settings.audio.min_chunk_duration * settings.audio.sample_rate)
        transcriptions = []
        
        for i in range(0, len(audio_array), chunk_length):
            chunk = audio_array[i:i + chunk_length]
            
            if len(chunk) < min_length:
                if len(chunk) > min_length // 2:
                    chunk = torch.nn.functional.pad(torch.tensor(chunk), (0, settings.audio.sample_rate - len(chunk)), value=0.0)
                else:
                    continue
            else:
                chunk = torch.tensor(chunk)
            
            result = self._process_audio_chunk(chunk, i // chunk_length)
            if result:
                transcriptions.append(result)
        
        final_transcription = " ".join(transcriptions)
        print(f"Final transcription length: {len(final_transcription)} characters")
        return final_transcription or "No speech detected in the audio file."

class ContentProcessor:
    def __init__(self):
        self.whisper_model = WhisperModel()
        self.storage = get_storage_provider()

    def _extract_video_id(self, url: str) -> Optional[str]:
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([^&\n?#]+)',
            r'youtube\.com/watch\?.*v=([^&\n?#]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _get_youtube_transcript(self, url: str) -> Tuple[Optional[str], bool]:
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return None, False
            
            ytt_api = YouTubeTranscriptApi()
            
            transcript_list = ytt_api.list(video_id)
            
            preferred_languages = ['en', 'vi']
            
            try:
                transcript = transcript_list.find_manually_created_transcript(preferred_languages)
                print(f"Found manually created transcript in {transcript.language} ({transcript.language_code})")
            except:
                try:
                    manual_transcripts = []
                    for t in transcript_list:
                        if not t.is_generated:
                            manual_transcripts.append(t.language_code)
                    
                    if manual_transcripts:
                        transcript = transcript_list.find_manually_created_transcript(manual_transcripts[:1])
                        print(f"Found manually created transcript in {transcript.language} ({transcript.language_code})")
                    else:
                        try:
                            transcript = transcript_list.find_generated_transcript(preferred_languages)
                            print(f"Found auto-generated transcript in {transcript.language} ({transcript.language_code})")
                        except:
                            generated_transcripts = []
                            for t in transcript_list:
                                if t.is_generated:
                                    generated_transcripts.append(t.language_code)
                            
                            if generated_transcripts:
                                transcript = transcript_list.find_generated_transcript(generated_transcripts[:1])
                                print(f"Found auto-generated transcript in {transcript.language} ({transcript.language_code})")
                            else:
                                print(f"No transcripts available for video {video_id}")
                                return None, False
                except:
                    print(f"No transcripts available for video {video_id}")
                    return None, False
            
            fetched_transcript = transcript.fetch()
            
            transcript_text = " ".join([snippet.text for snippet in fetched_transcript])
            
            if self._is_chat_transcript(transcript_text):
                print(f"Detected chat-like transcript for video {video_id}, skipping")
                return None, False
            
            print(f"Successfully retrieved transcript: {len(transcript_text)} characters, language: {transcript.language}")
            return transcript_text.strip(), True
            
        except Exception as e:
            print(f"Error getting transcript: {e}")
            return None, False

    def _is_chat_transcript(self, text: str) -> bool:
       
        text_lower = text.lower()
        
        chat_patterns = [
            r'\b\w+:\s',  # Username: message pattern
            r'@\w+',      # @mentions
            r'#\w+',      # hashtags
            r'\bemote\b', # emote references
            r'\bchat\b',  # direct chat references
            r'says:', 'said:', 'asks:', 'asked:'  # conversation indicators
        ]
        
        chat_indicator_count = 0
        total_patterns = len(chat_patterns)
        
        for pattern in chat_patterns:
            if re.search(pattern, text_lower):
                chat_indicator_count += 1
        
        chat_ratio = chat_indicator_count / total_patterns
        
        sentences = text.split('.')
        short_sentences = sum(1 for s in sentences if len(s.strip()) < 20)
        short_sentence_ratio = short_sentences / max(len(sentences), 1)
        
        return chat_ratio > 0.3 or short_sentence_ratio > 0.7

    async def process_pdf_docx(self, file_url: str) -> str:
        temp_file_url = None
        local_temp_path = None
        try:
            parser = LlamaParse(result_type="markdown", verbose=True)
        
            file_extension = self.storage.get_file_extension_from_url(file_url)
            from app.storages import get_storage_provider
            local_provider = get_storage_provider("local") 
            
            temp_file_url = self.storage.create_temp_file(file_extension)
            local_temp_path = local_provider._url_to_file_path(temp_file_url)
            
            async with httpx.AsyncClient(timeout=settings.content.request_timeout) as client:
                response = await client.get(file_url)
                response.raise_for_status()
                
                with open(local_temp_path, "wb") as f:
                    f.write(response.content)
            
            documents = parser.load_data(file_path=local_temp_path)
            
            return "\n\n".join([doc.text for doc in documents])
        
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"PDF/DOCX processing failed: {str(e)}")
        finally:
            if temp_file_url:
                self.storage.cleanup_temp_file(temp_file_url)


    async def process_image(self, file_url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=settings.content.request_timeout) as client:
                response = await client.get(file_url)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content))

            return pytesseract.image_to_string(image).strip()
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")
        

    async def process_web_url(self, url: str) -> str:
        try:
            headers = {'User-Agent': settings.content.user_agent}
            async with httpx.AsyncClient(timeout=settings.content.request_timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                for element in soup(["script", "style"]):
                    element.decompose()
                
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                return ' '.join(chunk for chunk in chunks if chunk)
            
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Web processing failed: {str(e)}")

    async def process_youtube_url(self, url: str) -> str:
        """Process YouTube URL - get transcript with preferred languages (en, vi) or any available transcript"""
        print(f"Processing YouTube URL: {url}")
        
        transcript_text, transcript_success = self._get_youtube_transcript(url)
        
        if transcript_success and transcript_text:
            print(f"Successfully obtained transcript from YouTube (length: {len(transcript_text)} characters)")
            return transcript_text
        
        raise HTTPException(
            status_code=400, 
            detail="No suitable YouTube transcript available. The video either has no transcripts, only stream/chat transcripts, or transcripts are disabled."
        )
        
    async def process_audio_video(self, file_url: str) -> str:
        try:
            print(f"Processing audio/video file: {file_url}")
            
            if not self.storage.file_exists(file_url):
                raise HTTPException(status_code=400, detail=f"Audio file not found: {file_url}")
            
            transcription = await self.whisper_model.transcribe_audio(file_url)
            return transcription or "No speech detected in the audio file."
            
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Audio/Video processing failed: {str(e)}")

content_processor = ContentProcessor()