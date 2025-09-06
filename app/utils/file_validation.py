from fastapi import HTTPException
from typing import List
from fastapi import UploadFile

MAX_BATCH_SIZE_MB = 50
MAX_BATCH_SIZE_BYTES = MAX_BATCH_SIZE_MB * 1024 * 1024

MAX_URLS_PER_BATCH = 2

def validate_single_file_size(file: UploadFile) -> None:
    if file.size and file.size > MAX_BATCH_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File size ({file.size / 1024 / 1024:.2f}MB) exceeds the maximum limit of {MAX_BATCH_SIZE_MB}MB"
        )
