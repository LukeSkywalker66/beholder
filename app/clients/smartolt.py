import requests
from app import config
from app.config import logger
from app.utils.safe_call import safe_call 

SMARTOLT_BASEURL = config.SMARTOLT_BASEURL
SMARTOLT_TOKEN = config.SMARTOLT_TOKEN


def _error_payload(detail: str, status_code=None):
    payload = {"status": False, "estado": "error", "detalle": detail}
    if status_code is not None:
        payload["status_code"] = status_code
    return payload


def _response_json_or_error(resp, context: str):
    try:
        return resp.json()
    except Exception as e:
        logger.error(f"Respuesta JSON invalida en {context}: {e}")
        return _error_payload(f"JSON invalido en {context}: {e}", getattr(resp, "status_code", None))


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
        return _error_payload(str(e))


def get_all_onus():
    try:
        """Devuelve el lote completo de ONUs desde SmartOLT."""
        resp = _request("GET", "/onu/get_all_onus_details")
        if not hasattr(resp, "json"):
            return []

        data = _response_json_or_error(resp, "get_all_onus")
        if not isinstance(data, dict):
            logger.error("SmartOLT devolvio un payload inesperado en get_all_onus")
            return []

        if not data.get("status"):
            logger.error("SmartOLT no devolvió estado OK")
            return []

        onus = data.get("onus", [])
        if not isinstance(onus, list):
            logger.error("Campo 'onus' invalido en get_all_onus")
            return []

        return onus
    except Exception as e:
        logger.error(f"Error al obtener listado de onus: {e}")
        return []
    

def get_onu_status(onu_id):
    try:
        resp = _request("GET", f"/onu/get_onu_status/{onu_id}")
        if not hasattr(resp, "json"):
            return resp

        data = _response_json_or_error(resp, f"get_onu_status/{onu_id}")
        if not isinstance(data, dict):
            logger.error(f"Payload inesperado en estado ONU {onu_id}")
            return _error_payload(f"Payload inesperado al consultar estado ONU {onu_id}")

        if not data.get("status"):
            logger.error(f"SmartOLT no devolvió estado OK para ONU {onu_id}")
        return data 
    except Exception as e:
        logger.error(f"Error al consultar estado ONU {onu_id}: {e}")
        return _error_payload(str(e))


def get_onu_signals(onu_id):
    try:
        resp = _request("GET", f"/onu/get_onu_signal/{onu_id}")
        if not hasattr(resp, "json"):
            return resp

        data = _response_json_or_error(resp, f"get_onu_signal/{onu_id}")
        if not isinstance(data, dict):
            logger.error(f"Payload inesperado en señales ONU {onu_id}")
            return _error_payload(f"Payload inesperado al consultar señales ONU {onu_id}")

        if not data.get("status"):
            logger.error(f"SmartOLT no devolvió estado OK para ONU {onu_id}")
        return data
    except Exception as e:
        logger.error(f"Error al consultar señales ONU {onu_id}: {e}")
        return _error_payload(str(e))
    
def get_attached_vlans(onu_id):
    """Obtiene las VLANs adjuntas de una ONU por external_id."""
    #lista el detalle de la onu, para sacar las attached vlans de sus serviceports
    
    resp = _request("GET", f"/onu/get_onu_details/{onu_id}")
    if not hasattr(resp, "json"):
        return []

    data = _response_json_or_error(resp, f"get_onu_details/{onu_id}")
    if not isinstance(data, dict):
        return []

    vlans = []
    if data.get("status"):
        onu_details = data.get("onu_details", {})
        serviceports = onu_details.get("service_ports", []) if isinstance(onu_details, dict) else []
        vlans = [sp["vlan"] for sp in serviceports if "vlan" in sp]

    return vlans