from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings  # noqa: F401 — ensures settings are validated on startup
from app.routers import auth

app = FastAPI(
    title="Renly API",
    description="Renly backend — personal finance (investments, metrics, exchange rates)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
def health():
    return {"status": "ok"}
