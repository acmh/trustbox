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

    down = client.get(f"/files/download/{token}", params={"public_key": "my-public-key"})
    assert down.status_code == 200
    assert down.headers["content-type"] == "application/octet-stream"
    assert down.headers["content-disposition"].startswith("attachment; filename=\"hello.txt\"")
    assert down.content == original_bytes


def test_download_not_found(client):
    missing = "deadbeef" * 8  # 64 hex chars
    resp = client.get(f"/files/download/{missing}", params={"public_key": "k"})
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

    resp = client.get(f"/files/download/{expired_token}", params={"public_key": "k"})
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

    resp = client.get(f"/files/download/{limited_token}", params={"public_key": "k"})
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

    resp = client.get(f"/files/download/{token}", params={"public_key": "wrong-key"})
    assert resp.status_code == 400


def test_upload_with_invalid_encrypted_policy_returns_400(client):
    files = {"file": ("hello.txt", b"hello", "text/plain")}
    # Provide an invalid policy_b64; server should respond 400
    data = {
        "public_key": "transport-key",
        "policy_b64": "not-base64!!",
    }
    resp = client.post("/files/upload", files=files, data=data)
    assert resp.status_code == 400


def test_download_get_does_not_increment_and_ack_increments(client, db_session):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    original_bytes = b"hello world"
    files = {"file": ("hello.txt", original_bytes, "text/plain")}
    data = {
        "public_key": "my-transport-key",
        # plaintext policy still supported by server, avoids heavy KDF in tests
        "max_downloads": "3",
        "expiration_date": future,
    }
    up = client.post("/files/upload", files=files, data=data)
    assert up.status_code == 200
    token = up.json()["download_token"]

    # GET download with correct transport key
    down = client.get(f"/files/download/{token}", params={"public_key": "my-transport-key"})
    assert down.status_code == 200
    assert down.content == original_bytes

    # Ensure count not incremented by GET
    rec = db_session.query(EncryptedFile).filter_by(download_token=token).first()
    assert rec is not None
    assert rec.download_count == 0

    # POST ack should increment
    ack = client.post(f"/files/download/ack/{token}")
    assert ack.status_code == 200
    rec = db_session.query(EncryptedFile).filter_by(download_token=token).first()
    assert rec.download_count == 1


def test_wrong_public_key_does_not_increment_count(client, db_session):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    files = {"file": ("hello.txt", b"hello world", "text/plain")}
    data = {
        "public_key": "correct-key",
        "max_downloads": "2",
        "expiration_date": future,
    }
    up = client.post("/files/upload", files=files, data=data)
    token = up.json()["download_token"]

    # Wrong key GET
    resp = client.get(f"/files/download/{token}", params={"public_key": "wrong-key"})
    assert resp.status_code == 400

    rec = db_session.query(EncryptedFile).filter_by(download_token=token).first()
    assert rec.download_count == 0


def test_ack_respects_limits(client, db_session):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    files = {"file": ("hello.txt", b"hello world", "text/plain")}
    data = {
        "public_key": "key",
        "max_downloads": "1",
        "expiration_date": future,
    }
    up = client.post("/files/upload", files=files, data=data)
    token = up.json()["download_token"]

    # First ack OK
    ack1 = client.post(f"/files/download/ack/{token}")
    assert ack1.status_code == 200

    # Second ack exceeds limit
    ack2 = client.post(f"/files/download/ack/{token}")
    assert ack2.status_code == 429


def test_ack_respects_expiration(client, db_session):
    expired_token = "z" * 64
    db_session.add(
        EncryptedFile(
            name="exp.txt",
            content=b"irrelevant",
            salt=b"irrelevant",
            key=b"irrelevant",
            max_downloads=5,
            expiration_date=datetime.now(timezone.utc) - timedelta(days=1),
            download_token=expired_token,
            download_count=0,
        )
    )
    db_session.commit()

    ack = client.post(f"/files/download/ack/{expired_token}")
    assert ack.status_code == 410
