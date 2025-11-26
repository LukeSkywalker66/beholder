from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app import config
from app.services.diagnostico import consultar_diagnostico

app = FastAPI(title="Beholder - Diagnóstico Centralizado")

@app.on_event("startup")
def startup_event():
    config.logger.info("Servicio Beholder iniciado.")

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    key = request.headers.get("x-api-key")
    if key != config.API_KEY:
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)

@app.get("/health")
def health():
    return {"ok": True, "service": "beholder", "status": "running"}

@app.get("/diagnosis/{pppoe_user}")
def diagnosis(pppoe_user: str):
    row = consultar_diagnostico(pppoe_user)
    if "error" in row:
        return JSONResponse(status_code=404, content={"detail": row["error"]})
    return row  # devuelve el dict completo con claves semánticas