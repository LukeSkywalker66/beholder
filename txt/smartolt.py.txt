import requests
from app import config
from app.config import logger
from app.utils.safe_call import safe_call 

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
    
def get_attached_vlans(onu_id):
    """Obtiene las VLANs adjuntas de una ONU por external_id."""
    #lista el detalle de la onu, para sacar las attached vlans de sus serviceports
    
    resp = _request("GET", f"/onu/get_onu_details/{onu_id}")
    data = resp.json()
    vlans = []
    if data.get("status"):
        serviceports = data["onu_details"].get("service_ports", [])
        vlans = [sp["vlan"] for sp in serviceports if "vlan" in sp]

    return vlans