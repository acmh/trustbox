import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# DATABASE_URL example:
# postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DB_NAME
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/trust_box",
)


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


