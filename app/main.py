from fastapi import FastAPI
from app.database import Base, engine
from app.routers.encrypted_files import router as files_router

app = FastAPI()
app.include_router(files_router)

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}
