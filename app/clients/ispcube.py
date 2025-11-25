import logging
import requests
from app import config

ISPCUBE_BASEURL = config.ISPCUBE_BASEURL
ISPCUBE_APIKEY = config.ISPCUBE_APIKEY
ISPCUBE_USER = config.ISPCUBE_USER
ISPCUBE_PASSWORD = config.ISPCUBE_PASSWORD
ISPCUBE_CLIENTID = config.ISPCUBE_CLIENTID

# Cache interno del token
_token_cache = None

def _obtener_token():
    """Solicita un nuevo token a ISPCube."""
    url = f"{ISPCUBE_BASEURL}/sanctum/token"
    payload = {"username": ISPCUBE_USER, "password": ISPCUBE_PASSWORD}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": ISPCUBE_APIKEY,
        "client-id": ISPCUBE_CLIENTID,
        "login-type": "api"
    }
    resp = requests.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()["token"]

def _get_token(force_refresh=False):
    """Devuelve un token válido, renovando si es necesario."""
    global _token_cache
    if force_refresh or _token_cache is None:
        _token_cache = _obtener_token()
    return _token_cache

def _headers(token=None):
    """Headers estándar para todas las llamadas."""
    return {
        "Authorization": f"Bearer {token or _get_token()}",
        "api-key": ISPCUBE_APIKEY,
        "client-id": ISPCUBE_CLIENTID,
        "login-type": "api",
        "Accept": "application/json",
        "username": ISPCUBE_USER
    }

def _request(method, url, **kwargs):
    """
    Wrapper de requests que maneja expiración de token.
    Si recibe 401, renueva token y reintenta una vez.
    """
    token = _get_token()
    headers = kwargs.pop("headers", {})
    headers.update(_headers(token))
    resp = requests.request(method, url, headers=headers, **kwargs)
    if resp.status_code == 401:
        # Token expirado → renovar y reintentar
        logging.warning("Token expirado, renovando...")
        token = _get_token(force_refresh=True)
        headers.update(_headers(token))
        resp = requests.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp

# ------------------ Funciones públicas ------------------

def obtener_nodos():
    """Devuelve lista de nodos con id, name, ip."""
    url = f"{ISPCUBE_BASEURL}/nodes/nodes_list"
    resp = _request("GET", url)
    body = resp.json()
    items = body["data"] if isinstance(body, dict) and "data" in body else body
    nodos = []
    for n in items:
        nodos.append({
            "id": n.get("id"),
            "name": n.get("comment"),
            "ip": n.get("ip")
        })
    return nodos

def obtener_conexion(pppoe):
    """Busca conexión por PPPoE y devuelve (conn_id, nodo_actual)."""
    url = f"{ISPCUBE_BASEURL}/connections?pppoe={pppoe}"
    resp = _request("GET", url)
    data = resp.json()
    if data:
        conn = data[0]
        return conn["id"], conn.get("node_id")
    raise RuntimeError(f"No se encontró conexión en ISPCube para {pppoe}")

def obtener_conexion_por_pppoe(pppoe_user):
    """
    Busca cliente por PPPoE y devuelve (conn_id, nodo_actual).
    """
    url = f"{ISPCUBE_BASEURL}/connection?user={pppoe_user}"
    resp = _request("GET", url)
    cliente = resp.json()

    conexiones = cliente.get("connections", [])
    if not conexiones:
        raise RuntimeError(f"No se encontraron conexiones para PPPoE {pppoe_user}")

    for conn in conexiones:
        if conn.get("conntype") == "pppoe" and conn.get("user") == pppoe_user:
            return conn["id"], conn.get("node_id")

    raise RuntimeError(f"No se encontró conexión PPPoE exacta para {pppoe_user}")


def obtener_todas_conexiones():
    """
    Devuelve lista de conexiones con datos básicos:
    user (PPPoE), customer_id, id (conn_id), node_id, plan_id.
    """
    url = f"{ISPCUBE_BASEURL}/connections/connections_list"
    resp = _request("GET", url)
    conexiones = resp.json()

    if not isinstance(conexiones, list):
        raise RuntimeError("Respuesta inesperada de ISPCube al listar conexiones")

    resultado = []
    for c in conexiones:
        if c.get("conntype") == "pppoe":
            resultado.append({
                "user": c.get("user"),
                "customer_id": c.get("customer_id"),
                "id": c.get("id"),
                "node_id": c.get("node_id"),
                "plan_id": c.get("plan_id")
            })
    return resultado

def obtener_planes():
    """
    Devuelve lista de planes con id, nombre, velocidad y descripción.
    """
    url = f"{ISPCUBE_BASEURL}/plans/plans_list"
    resp = _request("GET", url)
    planes = resp.json()

    if not isinstance(planes, list):
        raise RuntimeError("Respuesta inesperada de ISPCube al listar planes")

    resultado = []
    for p in planes:
        resultado.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "speed": p.get("speed"),
            "comment": p.get("comment")
        })
    return resultado