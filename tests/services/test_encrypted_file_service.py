from datetime import datetime, timezone, timedelta
import hashlib

from app.services.encrypted_file_service import EncryptedFileService
from app.models.encrypted_file import EncryptedFile


def test_save_file_persists_record(db_session):
    service = EncryptedFileService(db_session)
    now = datetime.now(timezone.utc)

    rec = service.save_file(
        name="file.txt",
        content=b"ciphertext",
        salt=b"salt123456789012",
        key=b"key-key-key-key-key-key-key-key",
        max_downloads=3,
        expiration_date=now + timedelta(days=1),
    )

    assert rec.id is not None
    assert rec.name == "file.txt"
    assert isinstance(rec.download_token, str) and len(rec.download_token) == 64

    fetched = db_session.query(EncryptedFile).filter(EncryptedFile.id == rec.id).first()
    assert fetched is not None
    assert fetched.download_token == rec.download_token


def test_save_file_retries_on_token_collision(db_session, monkeypatch):
    # Pre-insert a record with a known token digest to force a collision on first attempt
    existing_token_plain = "aaa"
    existing_digest = hashlib.sha256(existing_token_plain.encode()).hexdigest()
    db_session.add(
        EncryptedFile(
            name="exists.txt",
            content=b"c",
            salt=b"salt123456789012",
            key=b"k",
            max_downloads=1,
            expiration_date=datetime.now(timezone.utc) + timedelta(days=1),
            download_token=existing_digest,
        )
    )
    db_session.commit()

    service = EncryptedFileService(db_session)

    token_sequence = iter(["aaa", "bbb"])  # first collides, second succeeds

    def fake_new_token_b62(self, nbytes: int = 16):
        return next(token_sequence)

    monkeypatch.setattr(EncryptedFileService, "new_token_b62", fake_new_token_b62, raising=True)

    rec = service.save_file(
        name="new.txt",
        content=b"x",
        salt=b"salt123456789012",
        key=b"k",
        max_downloads=2,
        expiration_date=datetime.now(timezone.utc) + timedelta(days=1),
    )

    expected_digest = hashlib.sha256("bbb".encode()).hexdigest()
    assert rec.download_token == expected_digest
