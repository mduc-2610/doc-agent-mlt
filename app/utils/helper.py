import re
from fastapi import HTTPException, UploadFile

def clean_json_response(self, response_text: str) -> str:
    response_text = re.sub(r'```json\s*', '', response_text)
    response_text = re.sub(r'```\s*', '', response_text)

    start_idx = response_text.find('[')
    end_idx = response_text.rfind(']') + 1
    
    if start_idx != -1 and end_idx != -1:
        return response_text[start_idx:end_idx]
    return response_text.strip()

def detect_url_type(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "web"

def detect_file_type(file: UploadFile) -> str:
    audio_types = ['audio/mpeg', 'audio/wav', 'audio/mp3']
    video_types = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-msvideo']
    document_types = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff']
    
    if file.content_type in audio_types + video_types:
        return "audio_video"
    elif file.content_type in document_types + image_types:
        return "document"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")