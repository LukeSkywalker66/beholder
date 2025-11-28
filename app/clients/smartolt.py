import requests
from app import config
from app.config import logger

SMARTOLT_BASEURL = config.SMARTOLT_BASEURL
SMARTOLT_TOKEN = config.SMARTOLT_TOKEN

def _request(method, endpoint, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["X-Token"] = SMARTOLT_TOKEN
    url = f"{SMARTOLT_BASEURL}{endpoint}"
    resp = requests.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp

def get_all_onus():
    """Devuelve el lote completo de ONUs desde SmartOLT."""
    resp = _request("GET", "/onu/get_all_onus_details")
    data = resp.json()
    if not data.get("status"):
        logger.error("SmartOLT no devolvió estado OK")
    return data.get("onus", [])

def get_onu_status(onu_id):
    resp = _request("GET", f"/onu/get_onu_status/{onu_id}")
    data = resp.json()
    if not data.get("status"):
        logger.error(f"SmartOLT no devolvió estado OK para ONU {onu_id}")
    # Algunas APIs devuelven 'onu' o 'status' con detalles; retornamos el payload útil
    return data

def get_onu_signals(onu_id):
    resp = _request("GET", f"/onu/get_onu_signals/{onu_id}")
    data = resp.json()
    if not data.get("status"):
        logger.error(f"SmartOLT no devolvió estado OK para ONU {onu_id}")
    # Algunas APIs devuelven 'onu' o 'status' con detalles; retornamos el payload útil
    return data