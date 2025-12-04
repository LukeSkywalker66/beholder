Perfecto, Lucas 👁️. Para integrar **clientes de antenas** al backend y que aparezcan en tu diagnóstico junto con fibra, lo más ordenado es replicar el mismo patrón que ya tenés con SmartOLT e ISPCube, pero usando la API de **cnMaestro** de Cambium. Te desgloso el diseño:

---

## 🧩 Pasos de integración

### 1. Crear cliente `cnmaestro.py`
Un módulo en `app/clients/` que maneje la autenticación y llamadas a la API REST de cnMaestro.

Ejemplo básico:

```python
# app/clients/cnmaestro.py
import requests
from app import config
from app.config import logger

CNMAESTRO_BASEURL = config.CNMAESTRO_BASEURL
CNMAESTRO_USER = config.CNMAESTRO_USER
CNMAESTRO_PASS = config.CNMAESTRO_PASS

_token_cache = None

def _get_token():
    global _token_cache
    if _token_cache is None:
        url = f"{CNMAESTRO_BASEURL}/api/v1/access/token"
        resp = requests.post(url, json={"username": CNMAESTRO_USER, "password": CNMAESTRO_PASS})
        resp.raise_for_status()
        _token_cache = resp.json()["access_token"]
    return _token_cache

def _headers():
    return {"Authorization": f"Bearer {_get_token()}"}

def obtener_subscribers_aire():
    """
    Devuelve lista de suscriptores de antena desde cnMaestro.
    """
    url = f"{CNMAESTRO_BASEURL}/api/v1/devices/subscribers"
    resp = requests.get(url, headers=_headers())
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])
```

---

### 2. Crear tabla `subscribers_aire` en SQLite
En `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS subscribers_aire (
    id TEXT PRIMARY KEY,
    name TEXT,
    mac TEXT,
    ip TEXT,
    lat TEXT,
    lng TEXT,
    modelo TEXT,
    estado TEXT,
    cliente_id TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);
```

---

### 3. Métodos en `Database`
```python
def insert_subscriber_aire(self, id, name, mac, ip, lat, lng, modelo, estado, cliente_id=None):
    self.cursor.execute("""
        INSERT OR REPLACE INTO subscribers_aire
        (id, name, mac, ip, lat, lng, modelo, estado, cliente_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (id, name, mac, ip, lat, lng, modelo, estado, cliente_id))
```

---

### 4. Función de sincronización en `sync.py`
```python
from app.clients import cnmaestro

def sync_subscribers_aire(db):
    subs = cnmaestro.obtener_subscribers_aire()
    if subs:
        db.cursor.execute("DELETE FROM subscribers_aire")
        for s in subs:
            db.insert_subscriber_aire(
                s.get("id"),
                s.get("name"),
                s.get("mac"),
                s.get("ip"),
                s.get("latitude"),
                s.get("longitude"),
                s.get("model"),
                s.get("status"),
                s.get("customer_id")
            )
        db.commit()
        config.logger.info(f"[SYNC] {len(subs)} suscriptores aire sincronizados.")
        db.log_sync_status("cnmaestro", "ok", f"{len(subs)} suscriptores aire sincronizados")
    else:
        config.logger.warning("[SYNC] cnMaestro no devolvió suscriptores")
        db.log_sync_status("cnmaestro", "empty", "Sin datos de suscriptores aire")
```

---

### 5. Integrar en `nightly_sync`
```python
def nightly_sync():
    init_db()
    db = Database()
    try:
        sync_onus(db)
        sync_nodes(db)
        sync_plans(db)
        sync_connections(db)
        sync_clientes(db)
        sync_subscribers_aire(db)   # 👈 nuevo paso
        db.match_connections()
        db.commit()
        config.logger.info("[SYNC] Base actualizada con fibra y aire.")
    finally:
        db.close()
```

---

## ✅ Resultado
- Ahora tu diagnóstico puede mostrar tanto clientes de fibra (SmartOLT/ISPCube) como clientes de antena (cnMaestro).  
- La tabla `subscribers_aire` queda enlazada con `clientes` vía `cliente_id`.  
- El nightly sync mantiene todo actualizado.  

---

👉 ¿Querés que te arme también el `get_diagnosis` extendido para que, si el cliente es de antena, te devuelva los datos de `subscribers_aire` junto con el resto?



validar datos de cnmaestro