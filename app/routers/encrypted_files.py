from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from app.services.encryptor import Encryptor
from app.services.encrypted_file_service import EncryptedFileService
from app.models.encrypted_file import EncryptedFile
from app.database import get_db
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import hashlib
import re
import unicodedata
import urllib.parse
from cryptography.fernet import InvalidToken

router = APIRouter()

def build_content_disposition(filename: str) -> str:
    # ASCII fallback: normalize, remove diacritics, replace unsafe chars
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r"[^A-Za-z0-9._-]", "_", ascii_only) or "download"

    # RFC 5987 filename* with UTF-8 percent-encoding
    filename_star = urllib.parse.quote(filename, safe="")

    return f"attachment; filename=\"{ascii_only}\"; filename*=UTF-8''{filename_star}"

@router.post("/files/upload")
async def upload_file(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    public_key: str = Form(...),
    max_downloads: int = Form(...),
    expiration_date: datetime = Form(...),
    db: Session = Depends(get_db),
):
    provided = [(file is not None), (text is not None and text != "")]
    if sum(provided) != 1:
        raise HTTPException(status_code=400, detail="Provide exactly one of 'file' or 'text'")

    encryptor = Encryptor(public_key)

    if file is not None:
        raw_bytes = await file.read()
        display_name = file.filename
    else:
        raw_bytes = text.encode("utf-8")
        display_name = "message.txt"

    encrypted_content = encryptor.encrypt(raw_bytes)

    service = EncryptedFileService(db)
    record = service.save_file(
        name=display_name,
        content=encrypted_content,
        salt=encryptor.get_salt(),
        key=encryptor.get_key(),
        max_downloads=max_downloads,
        expiration_date=expiration_date,
    )

    return {
        "status_code": 200,
        "download_token": record.download_token,
    }

@router.post("/files/download/{token}")
def download_file_by_token(
    token: str,
    public_key: str = Form(...),
    db: Session = Depends(get_db),
):
    rec: EncryptedFile | None = db.query(EncryptedFile).filter_by(download_token=token).first()
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")

    now_utc = datetime.now(timezone.utc)
    rec_expiration = rec.expiration_date
    if rec_expiration.tzinfo is None:
        rec_expiration = rec_expiration.replace(tzinfo=timezone.utc)
    else:
        rec_expiration = rec_expiration.astimezone(timezone.utc)
    if rec_expiration <= now_utc:
        raise HTTPException(status_code=410, detail="Link expired")

    if rec.download_count >= rec.max_downloads:
        raise HTTPException(status_code=429, detail="Download limit reached")

    encryptor = Encryptor(public_key, salt=rec.salt)

    try:
        plaintext = encryptor.decrypt(rec.content)
        content_disposition = build_content_disposition(rec.name)

        # Only increment on successful preparation
        rec.download_count += 1
        db.commit()

        return StreamingResponse(
            BytesIO(plaintext),
            media_type="application/octet-stream",
            headers={"Content-Disposition": content_disposition},
        )
    except InvalidToken:
        db.rollback()
        raise HTTPException(status_code=401, detail="Incorrect password")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error while preparing download")
