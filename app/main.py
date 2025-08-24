from fastapi import FastAPI
from app.database import Base, engine
from app.routers.encrypted_files import router as files_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(files_router)

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}
