import os
import tempfile
import subprocess
import traceback
from typing import Optional
from fastapi import HTTPException, UploadFile
from llama_cloud_services import LlamaParse
from PIL import Image
import pytesseract
from bs4 import BeautifulSoup
import requests
import yt_dlp
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import torch
import librosa
from app.config import settings

class WhisperModel:
    def __init__(self):
        self.processor = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
    
    def load_model(self):
        if self.processor is None:
            self.processor = WhisperProcessor.from_pretrained("openai/whisper-base")
            self.model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-base")
            self.model.to(self.device)
    
    def transcribe_audio(self, audio_path: str) -> str:
        self.load_model()
        audio_array, sampling_rate = librosa.load(audio_path, sr=16000)
        inputs = self.processor([audio_array], sampling_rate=sampling_rate, return_tensors="pt", padding=True)
        input_features = inputs.input_features.to(self.device)
        
        with torch.no_grad():
            predicted_ids = self.model.generate(input_features)
        
        transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)
        return transcription[0] if transcription else ""

whisper_model = WhisperModel()

def save_content_to_file(content: str, document_id: str) -> str:
    """Save content to file and return file path"""
    os.makedirs(settings.content_files_dir, exist_ok=True)
    file_path = os.path.join(settings.content_files_dir, f"{document_id}.txt")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return file_path

def save_temp_file(file: UploadFile) -> str:
    os.makedirs(settings.temp_files_dir, exist_ok=True)
    temp_file_path = os.path.join(settings.temp_files_dir, file.filename)
    with open(temp_file_path, "wb") as buffer:
        contents = file.file.read()
        buffer.write(contents)
    return temp_file_path

def convert_audio_to_wav(input_path: str) -> str:
    output_path = input_path.rsplit('.', 1)[0] + '.wav'
    
    try:
        command = ['ffmpeg', '-i', input_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', output_path, '-y']
        subprocess.run(command, check=True, capture_output=True)
        return output_path
    except subprocess.CalledProcessError as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Audio conversion failed: {str(e)}")

def process_pdf_docx(file_path: str) -> str:
    try:
        parser = LlamaParse(result_type="markdown", verbose=True)
        documents = parser.load_data(file_path=file_path)
        return "\n\n".join([doc.text for doc in documents])
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF/DOCX processing failed: {str(e)}")

def process_image(file_path: str) -> str:
    try:
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")

def process_web_url(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Web processing failed: {str(e)}")

def download_youtube_video(url: str) -> str:
    temp_dir = tempfile.mkdtemp()
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'extractaudio': True,
        'audioformat': 'wav',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base_path = filename.rsplit('.', 1)[0]
            
            for ext in ['.wav', '.mp3', '.m4a', '.webm']:
                if os.path.exists(base_path + ext):
                    audio_path = base_path + ext
                    break
            else:
                raise FileNotFoundError("Downloaded audio file not found")
            
            if not audio_path.endswith('.wav'):
                audio_path = convert_audio_to_wav(audio_path)
            
            return audio_path
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"YouTube download failed: {str(e)}")

def process_audio_video(file_path: str) -> str:
    try:
        if not file_path.endswith('.wav'):
            file_path = convert_audio_to_wav(file_path)
        
        transcription = whisper_model.transcribe_audio(file_path)
        return transcription
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Audio/Video processing failed: {str(e)}")