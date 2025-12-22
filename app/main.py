from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from app import config
from app.services.diagnostico import consultar_diagnostico
from app.security import get_api_key
from app.db.sqlite import Database # Importación necesaria
from app.config import logger
from app.clients import mikrotik
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

@app.get("/live/{pppoe_user}")
def live_traffic(pppoe_user: str):
    """
    Obtiene el consumo en tiempo real resolviendo internamente 
    en qué nodo está el cliente.
    """
    db = Database()
    try:
        # 1. Buscamos la IP del router en nuestra DB local
        router_data = db.get_router_for_pppoe(pppoe_user)
        
        if not router_data:
            # Si no está en la tabla connections, no sabemos a qué router preguntarle
            return {
                "status": "error", 
                "detail": "Cliente no vinculado o no encontrado en base de datos local."
            }
            
        router_ip, router_port = router_data
        
        # Usamos puerto default si la DB lo tiene null/vacío
        if not router_port:
            router_port = config.MK_PORT
        
        # 2. Consultamos al Mikrotik
        trafico = mikrotik.obtener_trafico_en_vivo(router_ip, pppoe_user, int(router_port))
        
        if "error" in trafico:
             return {"status": "error", "detail": trafico["error"]}
             
        # 3. Formateamos respuesta
        rx_mbps = round(int(trafico["rx"]) / 1000000, 2)
        tx_mbps = round(int(trafico["tx"]) / 1000000, 2)
        
        return {
            "status": "ok",
            "router_ip": router_ip, # Dato útil para debug, opcional
            "download_mbps": rx_mbps,
            "upload_mbps": tx_mbps,
            "raw": trafico
        }
        
    except Exception as e:
        config.logger.error(f"Fallo endpoint live traffic: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()