import re
import json
import logging
from fastapi import HTTPException, File, Form, UploadFile
from typing import get_origin, get_args

logger = logging.getLogger(__name__)

def clean_json_response(response_text: str) -> list:
    """Enhanced JSON parsing with multiple fallback strategies"""
    try:
        if not response_text or not response_text.strip():
            return []
            
        # Remove code block markers
        text = re.sub(r'```(?:json)?', '', response_text)
        text = text.strip()
        
        # Strategy 1: Direct JSON parsing
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract JSON array/object from text
        json_patterns = [
            r'\[.*\]',  # Array pattern
            r'\{.*\}',  # Object pattern  
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        return [data]
                except json.JSONDecodeError:
                    continue
        
        # Strategy 3: Clean and fix common JSON issues
        try:
            # Remove leading/trailing non-JSON content
            text = re.sub(r'^[^[\{]*', '', text)
            text = re.sub(r'[^}\]]*$', '', text)
            
            # Fix common issues
            text = re.sub(r'(\w+):', r'"\1":', text)  # Unquoted keys
            text = re.sub(r"'([^']*)'", r'"\1"', text)  # Single quotes
            text = re.sub(r',(\s*[}\]])', r'\1', text)  # Trailing commas
            text = re.sub(r'"\s*\n\s*"', r'" "', text)  # Line breaks in strings
            
            data = json.loads(text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
        except:
            pass
        
        # Strategy 4: Extract individual objects
        objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        valid_objects = []
        
        for obj_str in objects:
            try:
                # Clean the object string
                fixed = obj_str.strip()
                fixed = re.sub(r'(\w+):', r'"\1":', fixed)
                fixed = re.sub(r"'([^']*)'", r'"\1"', fixed)
                fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
                
                obj = json.loads(fixed)
                valid_objects.append(obj)
            except:
                continue
        
        return valid_objects
        
    except Exception as e:
        logger.debug(f"JSON parsing failed: {e}")
        return []

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
        elif field_type == UploadFile or (hasattr(field_type, '__name__') and 'UploadFile' in field_type.__name__):
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