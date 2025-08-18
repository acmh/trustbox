# Trust Box

A FastAPI service to securely encrypt uploaded files and store them in PostgreSQL. Each upload returns a short, unguessable download token. Downloads require the correct public key to decrypt.

## Features
- Upload a file via multipart form; content is encrypted with a key derived from a provided public key
- Short token for download links
- Download endpoint enforces expiration date and maximum download count
- PostgreSQL persistence via SQLAlchemy

## Project structure
```
app/
  main.py
  database.py
  models/
    encrypted_file.py
  routers/
    encrypted_files.py
  services/
    encryptor.py
Dockerfile
docker_compose.yml
requirements.txt
```

## Requirements
- Docker and Docker Compose v2 (use `docker compose ...`)
- Or Python 3.12+ (for local dev without Docker)

## Quick start (Docker Compose)
The Compose file name is `docker_compose.yml` (note the underscore), so use `-f`.

```bash
# From repo root
docker compose -f docker_compose.yml up -d --build
# App: http://localhost:8000
```

Services:
- db: PostgreSQL 15, port 5432 exposed
- app: FastAPI, port 8000 exposed, source mounted with live reload

Environment inside the app container:
- `DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/trust_box`

Logs:
```bash
docker compose -f docker_compose.yml logs -f app
```

Stop:
```bash
docker compose -f docker_compose.yml down
```

## Local development (without Docker)
```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Option A: use PostgreSQL running on localhost (start your own DB or run: docker compose -f docker_compose.yml up -d db)
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/trust_box"

# Option B: quick start with SQLite (no external DB needed)
# export DATABASE_URL="sqlite+pysqlite:///./dev.db"

uvicorn app.main:app --reload
# http://localhost:8000
```

## API
### Upload a file
POST `/files/upload`
- Form fields:
  - `file` (file): the file to upload
  - `public_key` (str): used to derive the encryption key
  - `max_downloads` (int)
  - `expiration_date` (ISO 8601 datetime, e.g. `2025-12-31T23:59:59Z`)

Example:
```bash
curl -X POST http://localhost:8000/files/upload \
  -F "file=@/absolute/path/to/file.txt;type=text/plain" \
  -F "public_key=your-public-key-string" \
  -F "max_downloads=3" \
  -F "expiration_date=2025-12-31T23:59:59Z"
```
Response:
```json
{
  "status_code": 200,
  "download_token": "AbCdEfGhIj" 
}
```

### Download a file by token
GET `/files/download/{token}?public_key=...`

- Validates:
  - Token exists
  - Not expired
  - Download count has not exceeded `max_downloads`
  - Public key can decrypt the file

Example:
```bash
curl -G "http://localhost:8000/files/download/REPLACE_TOKEN" \
  --data-urlencode "public_key=your-public-key-string" \
  -o downloaded_file
```

## Environment variables
- `DATABASE_URL`: SQLAlchemy URL.
  - Postgres (psycopg2): `postgresql+psycopg2://USER:PASS@HOST:5432/DB`
  - Postgres (psycopg3): `postgresql+psycopg://USER:PASS@HOST:5432/DB` (requires psycopg 3)
  - SQLite: `sqlite+pysqlite:///./dev.db`

## Migrations (optional)
This project currently creates tables on startup. To manage schema with Alembic:
1) Install Alembic in your environment or add to `requirements.txt`:
```bash
pip install alembic
```
2) Configure `alembic.ini` with a default URL (env var overrides are supported in `env.py`).
3) In `alembic/env.py`, ensure:
```python
from app.database import Base
from app.models.encrypted_file import EncryptedFile  # import models so metadata is populated
 target_metadata = Base.metadata
```
4) Generate and apply migrations (inside the app container or your venv):
```bash
alembic revision --autogenerate -m "create encrypted_files"
alembic upgrade head
```

To run Alembic automatically before app start in Docker, you can change the app command in compose to:
```yaml
command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
```

## Troubleshooting
- "Can't load plugin: sqlalchemy.dialects:driver": Your `DATABASE_URL` is invalid. Use a real dialect+driver, e.g. `postgresql+psycopg2://...` or `sqlite+pysqlite:///...`.
- "The asyncio extension requires an async driver": You’re using an async URL/engine with a sync driver (`psycopg2`). Use sync everywhere (recommended) or switch to async driver (`asyncpg`) and refactor for async sessions.
- "Failed to open/read local data from file/application" with curl: Ensure you pass a valid absolute path (e.g., `/Users/...`), not `./Users/...`. If running curl inside the container, copy the file into the container first or mount it via the compose bind mount.

## License
MIT (or your preferred license).
