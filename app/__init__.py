from celery import Celery
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

# Celery configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery_app = Celery(
    "trust_box",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.beat_schedule = {
    # Every 10 minutes cleanup expired or over-downloaded entries
    "cleanup-expired-entries": {
        "task": "app.cleanup.cleanup_expired",
        "schedule": 600.0,
    },
}
