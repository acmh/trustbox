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
import base64
import json
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

router = APIRouter()

@router.post("/files/upload")
async def upload_file(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    public_key: str = Form(...),
    max_downloads: int | None = Form(default=None),
    expiration_date: datetime | None = Form(default=None),
    policy_b64: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    provided = [(file is not None), (text is not None and text != "")]
    if sum(provided) != 1:
        raise HTTPException(status_code=400, detail="Provide exactly one of 'file' or 'text'")

    # Decrypt policy if provided (policy_b64 packs: salt(16) | iv(12) | ciphertext)
    if policy_b64 is not None:
        try:
            packed = base64.b64decode(policy_b64)
            if len(packed) < 28:
                raise ValueError("policy packed too short")
            salt = packed[:16]
            iv = packed[16:28]
            ciphertext = packed[28:]
            # KDF PBKDF2-HMAC-SHA256 iterations must match frontend
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=1_200_000)
            key = kdf.derive(public_key.encode("utf-8"))
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None)
            policy_json = json.loads(plaintext.decode("utf-8"))
            if isinstance(policy_json, dict):
                # Override values if present
                if policy_json.get("maxDownloads") is not None:
                    max_downloads = int(policy_json["maxDownloads"])  # type: ignore
                if policy_json.get("expirationDate") is not None:
                    # ISO date string expected
                    expiration_date = datetime.fromisoformat(policy_json["expirationDate"])  # type: ignore
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid encrypted policy")

    if max_downloads is None or expiration_date is None:
        raise HTTPException(status_code=400, detail="Missing policy: max_downloads/expiration_date")

    encryptor = Encryptor(public_key)

    if file is not None:
        raw_bytes = await file.read()
        display_name = file.filename
    else:
        raw_bytes = text.encode("utf-8")
        display_name = "message.txt"

    # Enforce max original size = 2MB. If TBX package is detected, read original size from meta.size
    MAX_BYTES = 2 * 1024 * 1024
    original_size = None
    try:
        if file is not None and len(raw_bytes) >= 8 and raw_bytes[:4] == b"TBX1":
            meta_len = int.from_bytes(raw_bytes[4:8], "big")
            meta_start = 8
            meta_end = meta_start + meta_len
            if meta_end + 28 <= len(raw_bytes):
                meta_json = json.loads(raw_bytes[meta_start:meta_end].decode("utf-8"))
                size_field = meta_json.get("size")
                if isinstance(size_field, int):
                    original_size = size_field
    except Exception:
        # If TBX parsing fails, fall back to raw length check below
        pass

    if original_size is None:
        original_size = len(raw_bytes)

    if original_size > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 2MB.")

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

    return StreamingResponse(
        BytesIO(plaintext),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{rec.name}"'},
    )

@router.post("/files/download/ack/{token}")
def acknowledge_successful_download(
    token: str,
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

    rec.download_count += 1
    db.commit()

    return {"status": "ok"}
