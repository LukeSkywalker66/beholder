from fastapi import FastAPI, Request, HTTPException
from app import config

app = FastAPI(title="Beholder - Diagnóstico Centralizado")

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    key = request.headers.get("x-api-key")
    if key != config.API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")
    return await call_next(request)

@app.get("/health")
def health():
    return {"ok": True, "service": "beholder", "status": "running"}