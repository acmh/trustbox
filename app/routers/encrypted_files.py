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

router = APIRouter()

@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    public_key: str = Form(...),
    max_downloads: int = Form(...),
    expiration_date: datetime = Form(...),
    db: Session = Depends(get_db),
):
    encryptor = Encryptor(public_key)

    file_content = await file.read()
    encrypted_content = encryptor.encrypt(file_content)

    service = EncryptedFileService(db)
    record = service.save_file(
        name=file.filename,
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

@router.get("/files/download/{token}")
def download_file_by_token(
    token: str,
    public_key: str,
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
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid public key or corrupted file")

    rec.download_count += 1
    db.commit()

    return StreamingResponse(
        BytesIO(plaintext),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{rec.name}"'},
    )
