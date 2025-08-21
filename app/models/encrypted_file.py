from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, LargeBinary, DateTime
from app.database import Base


class EncryptedFile(Base):
    __tablename__ = "encrypted_files"

    id = Column(Integer, primary_key=True, index=True)
    download_token = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    content = Column(LargeBinary, nullable=False)
    salt = Column(LargeBinary, nullable=False)
    key = Column(LargeBinary, nullable=False)
    max_downloads = Column(Integer, nullable=False)
    expiration_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    download_count = Column(Integer, default=0, nullable=False)


