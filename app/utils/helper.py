import re
import json
from fastapi import HTTPException, UploadFile, File, Form, UploadFile
from typing import List, Dict, Any
from fastapi import Depends, Form, File, UploadFile, HTTPException
from fastapi.datastructures import UploadFile as UploadFileType
from pydantic import BaseModel
from typing import Type, Optional, Dict, Any
from inspect import signature
from typing import get_origin, get_args

def clean_json_response(response_text: str) -> str:
    """Clean and extract JSON from model response"""
    response_text = re.sub(r'```json\s*', '', response_text)
    response_text = re.sub(r'```\s*', '', response_text)

    start_idx = response_text.find('[')
    end_idx = response_text.rfind(']') + 1
    
    if start_idx != -1 and end_idx != -1:
        return response_text[start_idx:end_idx]
    return response_text.strip()

def detect_url_type(url: str) -> str:
    """Detect the type of URL for processing"""
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "web"

def detect_file_type(file: UploadFile) -> str:
    """Detect file type for processing"""
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

def as_form(cls):
    fields = cls.model_fields
    
    params = []
    annotations = {}
    
    for field_name, field_info in fields.items():
        field_type = field_info.annotation
        default_val = field_info.default
        
        if get_origin(field_type) is type(None.__class__.__bases__[0]) and len(get_args(field_type)) == 2:
            inner_type = get_args(field_type)[0]
            if inner_type == str:
                params.append(f"{field_name}: Optional[str] = Form({repr(default_val)})")
            else:
                params.append(f"{field_name}: Optional[{inner_type.__name__}] = Form({repr(default_val)})")
        elif field_type == UploadFile:
            params.append(f"{field_name}: UploadFile = File(...)")
        elif field_type == str:
            params.append(f"{field_name}: str = Form(...)")
        elif field_type == int:
            params.append(f"{field_name}: int = Form({default_val})")
        else:
            params.append(f"{field_name}: {field_type.__name__} = Form(...)")
    
    func_def = f"""
async def dependency({', '.join(params)}):
    return cls(**{{{', '.join([f'"{f}": {f}' for f in fields.keys()])}}})
"""
    
    namespace = {
        'cls': cls, 
        'Form': Form, 
        'File': File, 
        'UploadFile': UploadFile,
        'Optional': type(None).__class__.__bases__[0]
    }
    exec(func_def, namespace)
    
    return namespace['dependency']