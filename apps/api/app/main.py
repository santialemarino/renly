from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings  # noqa: F401 — ensures settings are validated on startup
from app.domain import NotFoundError
from app.routers import auth, investments

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
app.include_router(investments.router)


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(_request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
