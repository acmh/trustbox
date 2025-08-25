from datetime import datetime, timezone, timedelta

from app.models.encrypted_file import EncryptedFile


def test_upload_file_success(client):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    files = {"file": ("hello.txt", b"hello world", "text/plain")}
    data = {
        "public_key": "my-public-key",
        "max_downloads": "3",
        "expiration_date": future,
    }

    resp = client.post("/files/upload", files=files, data=data)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status_code"] == 200
    assert isinstance(body["download_token"], str) and len(body["download_token"]) == 64


def test_download_success_roundtrip(client):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    original_bytes = b"hello world"
    files = {"file": ("hello.txt", original_bytes, "text/plain")}
    data = {
        "public_key": "my-public-key",
        "max_downloads": "3",
        "expiration_date": future,
    }

    up = client.post("/files/upload", files=files, data=data)
    token = up.json()["download_token"]

    down = client.post(f"/files/download/{token}", data={"public_key": "my-public-key"})
    assert down.status_code == 200
    assert down.headers["content-type"] == "application/octet-stream"
    assert down.headers["content-disposition"].startswith("attachment; filename=\"hello.txt\"")
    assert down.content == original_bytes


def test_download_not_found(client):
    missing = "deadbeef" * 8  # 64 hex chars
    resp = client.post(f"/files/download/{missing}", data={"public_key": "k"})
    assert resp.status_code == 404


def test_download_expired(client, db_session):
    expired_token = "x" * 64
    db_session.add(
        EncryptedFile(
            name="exp.txt",
            content=b"irrelevant",
            salt=b"irrelevant",
            key=b"irrelevant",
            max_downloads=1,
            expiration_date=datetime.now(timezone.utc) - timedelta(days=1),
            download_token=expired_token,
            download_count=0,
        )
    )
    db_session.commit()

    resp = client.post(f"/files/download/{expired_token}", data={"public_key": "k"})
    assert resp.status_code == 410


def test_download_limit_reached(client, db_session):
    limited_token = "y" * 64
    db_session.add(
        EncryptedFile(
            name="lim.txt",
            content=b"irrelevant",
            salt=b"irrelevant",
            key=b"irrelevant",
            max_downloads=1,
            expiration_date=datetime.now(timezone.utc) + timedelta(days=1),
            download_token=limited_token,
            download_count=1,
        )
    )
    db_session.commit()

    resp = client.post(f"/files/download/{limited_token}", data={"public_key": "k"})
    assert resp.status_code == 429


def test_download_invalid_key(client):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    files = {"file": ("hello.txt", b"hello world", "text/plain")}
    data = {
        "public_key": "correct-key",
        "max_downloads": "1",
        "expiration_date": future,
    }

    up = client.post("/files/upload", files=files, data=data)
    token = up.json()["download_token"]

    resp = client.post(f"/files/download/{token}", data={"public_key": "wrong-key"})
    assert resp.status_code == 401
