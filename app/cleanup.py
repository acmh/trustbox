from datetime import datetime, timezone
from sqlalchemy import create_engine, text
import os
from .database import DATABASE_URL
from . import celery_app

BATCH_SIZE = int(os.getenv("CLEANUP_BATCH_SIZE", "500"))

@celery_app.task(name="app.cleanup.cleanup_expired")
def cleanup_expired():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    now_utc = datetime.now(timezone.utc)
    # Delete in batches to avoid long locks; loop until no rows deleted
    total_deleted = 0
    with engine.begin() as conn:
        while True:
            # Expired by date
            res = conn.execute(
                text(
                    """
                    DELETE FROM encrypted_files
                    WHERE id IN (
                      SELECT id FROM encrypted_files
                      WHERE expiration_date <= :now
                      LIMIT :batch
                    )
                    """
                ),
                {"now": now_utc, "batch": BATCH_SIZE},
            )
            deleted = res.rowcount or 0
            total_deleted += deleted
            if deleted < BATCH_SIZE:
                break
        # Also delete where download_count >= max_downloads
        while True:
            res = conn.execute(
                text(
                    """
                    DELETE FROM encrypted_files
                    WHERE id IN (
                      SELECT id FROM encrypted_files
                      WHERE download_count >= max_downloads
                      LIMIT :batch
                    )
                    """
                ),
                {"batch": BATCH_SIZE},
            )
            deleted = res.rowcount or 0
            total_deleted += deleted
            if deleted < BATCH_SIZE:
                break
    return {"deleted": total_deleted}
