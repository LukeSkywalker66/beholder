
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from app import config
from app.services.diagnostico import consultar_diagnostico
from app.security import get_api_key
from fastapi import FastAPI, Depends
from app.config import logger


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
    try:
        row = consultar_diagnostico(pppoe_user)
    except Exception as e:
        logger.exception(f"Error en diagnóstico de {pppoe_user}")
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in row:
        raise HTTPException(status_code=404, detail=row["error"])
    return row

    
    # row = consultar_diagnostico(pppoe_user)
    # if "error" in row:
    #     return JSONResponse(status_code=404, content={"detail": row["error"]})
    # return row  # devuelve el dict completo con claves semánticas

@app.get("/")
def read_root(api_key: str = Depends(get_api_key)):
    return {"status": "ok", "service": "Beholder API"}
