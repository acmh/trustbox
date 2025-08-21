import secrets, hashlib
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
            token = self.new_token_b62()
            rec = EncryptedFile(
                name=name,
                content=content,
                salt=salt,
                key=key,
                max_downloads=max_downloads,
                expiration_date=expiration_date,
                download_token=self.token_digest(token)
            )
            self.db_session.add(rec)
            try:
                self.db_session.commit()
                self.db_session.refresh(rec)
                return rec
            except IntegrityError:
                self.db_session.rollback()
        raise RuntimeError("Failed to generate unique download token")

    def new_token_b62(self, nbytes: int = 16) -> str:
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        n = int.from_bytes(secrets.token_bytes(nbytes), "big")
        out = []
        while n:
            n, r = divmod(n, 62)
            out.append(alphabet[r])
        return "".join(reversed(out)) or "0"

    def token_digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
