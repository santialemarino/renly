from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings  # noqa: F401 — ensures settings are validated on startup
from app.domain import NotFoundError
from app.routers import auth, exchange_rates, groups, investments, metrics, snapshot_grid
from app.routers import settings as settings_router
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Renly API",
    description="Renly backend — personal finance (investments, metrics, exchange rates)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(exchange_rates.router)
app.include_router(groups.router)
app.include_router(investments.router)
app.include_router(metrics.router)
app.include_router(settings_router.router)
app.include_router(snapshot_grid.router)


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(_request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
