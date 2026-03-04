from fastapi import FastAPI

app = FastAPI(
    title="Renly API",
    description="Renly backend — personal finance (investments, metrics, exchange rates)",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}
