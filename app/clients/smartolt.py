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
        logger.Error("SmartOLT no devolvió estado OK")
    return data.get("onus", [])