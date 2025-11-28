import requests
from app import config
from app.config import logger

SMARTOLT_BASEURL = config.SMARTOLT_BASEURL
SMARTOLT_TOKEN = config.SMARTOLT_TOKEN

def _request(method, endpoint, **kwargs):
    try:
        headers = kwargs.pop("headers", {})
        headers["X-Token"] = SMARTOLT_TOKEN
        url = f"{SMARTOLT_BASEURL}{endpoint}"
        resp = requests.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.error(f"Error en request API smartOLT: {e}")
        return {"estado": "error", "API smartOLT detalle": str(e)}
    
def get_all_onus():
    try:
        """Devuelve el lote completo de ONUs desde SmartOLT."""
        resp = _request("GET", "/onu/get_all_onus_details")
        data = resp.json() # type : ignore
        if not data.get("status"):
            logger.error("SmartOLT no devolvió estado OK")
        return data.get("onus", [])
    except Exception as e:
        logger.error(f"Error al obtener listado de onus: {e}")
        return {"estado": "error", "API smartOLT detalle": str(e)}
    
def get_onu_status(onu_id):
    try:
        resp = _request("GET", f"/onu/get_onu_status/{onu_id}")
        data = resp.json() # type : ignore
        if not data.get("status"):
            logger.error(f"SmartOLT no devolvió estado OK para ONU {onu_id}")
        return data 
    except Exception as e:
        logger.error(f"Error al consultar estado ONU {onu_id}: {e}")
        return {"estado": "error", "API smartOLT, detalle": str(e)}
    
def get_onu_signals(onu_id):
    try:
        resp = _request("GET", f"/onu/get_onu_signal/{onu_id}")
        data = resp.json()  # type : ignore
        if not data.get("status"):
            logger.error(f"SmartOLT no devolvió estado OK para ONU {onu_id}")
        return data
    except Exception as e:
        logger.error(f"Error al consultar señales ONU {onu_id}: {e}")
        return {"estado": "error", "API smartOLT, detalle": str(e)}
