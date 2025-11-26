from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app import config
from app.db.sqlite import init_db, get_subscriber_by_pppoe

app = FastAPI(title="Beholder - Diagnóstico Centralizado")

@app.on_event("startup")
def startup_event():
    init_db()

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    key = request.headers.get("x-api-key")
    if key != config.API_KEY:
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)

@app.get("/health")
def health():
    return {"ok": True, "service": "beholder", "status": "running"}

@app.get("/subscribers/{pppoe_user}")
def get_subscriber(pppoe_user: str):
    row = get_subscriber_by_pppoe(pppoe_user)
    if not row:
        return JSONResponse(status_code=404, content={"detail": "subscriber not found"})
    return {
        "pppoe_user": row[0],
        "external_id": row[1],
        "onu_id": row[2],
        "node_code": row[3],
        "vlan_info": row[4],
        "updated_at": row[5],
    }