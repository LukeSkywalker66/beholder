from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from app import config
from app.services.diagnostico import consultar_diagnostico
from app.security import get_api_key
from app.db.sqlite import Database # Importación necesaria
from app.config import logger
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Beholder - Diagnóstico Centralizado")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    config.logger.info("Servicio Beholder iniciado.")

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
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

# --- NUEVO ENDPOINT DE BÚSQUEDA ---
@app.get("/search")
def search_clients(q: str):
    """
    Busca clientes por nombre, dirección o PPPoE (Gestión + OLT).
    """
    if not q or len(q) < 3:
        return []
    
    db = Database()
    try:
        results = db.search_client(q)
        return results
    except Exception as e:
        logger.exception(f"Error buscando cliente: {q}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/")
def read_root(api_key: str = Depends(get_api_key)):
    return {"status": "ok", "service": "Beholder API"}