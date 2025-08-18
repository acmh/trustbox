import secrets
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.encrypted_file import EncryptedFile

class EncryptedFileService:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def save_file(
        self, *, name: str, content: bytes, salt: bytes, key: bytes,
        max_downloads: int, expiration_date
    ) -> EncryptedFile:
    
        for _ in range(5):  # retry on rare token collisions
            token = secrets.token_urlsafe(12)
            rec = EncryptedFile(
                name=name,
                content=content,
                salt=salt,
                key=key,
                max_downloads=max_downloads,
                expiration_date=expiration_date,
                download_token=token
            )
            self.db_session.add(rec)
            try:
                self.db_session.commit()
                self.db_session.refresh(rec)
                return rec
            except IntegrityError:
                self.db_session.rollback()
        raise RuntimeError("Failed to generate unique download token")