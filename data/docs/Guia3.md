

# 📖 Documentación Backend Beholder

## 1. Introducción
Beholder es una API de diagnóstico centralizado para clientes ISP (fibra y antena).  
Su backend combina:
- **FastAPI** para exponer endpoints REST.  
- **SQLite** como base local de sincronización.  
- **Integraciones externas** con SmartOLT, ISPCube, Mikrotik y GenieACS.  
- **Proceso nocturno de sincronización** que actualiza la base con datos de las APIs externas.  

---

## 2. Entorno de Producción
- **Servidor Debian**  
  - Código: `/home/administrador/apps/beholder`  
  - Repositorio Git: `/home/administrador/repos/beholder.git`  
  - Servicio systemd: `/etc/systemd/system/beholder.service`  
  - Configuración Nginx: `/etc/nginx/sites-enabled/beholder.conf`  
  - Logs: `/var/log/beholder/`  

- **Deploy**  
  - `git push production main` → hook → reload nginx + restart beholder.service.  
  - Sudoers configurado con NOPASSWD para `systemctl reload nginx` y `systemctl restart beholder.service`.  

---

## 3. Estructura del Backend
```
app/
├── main.py              # FastAPI, endpoints /diagnosis y /health
├── config.py            # Variables de entorno, logging centralizado
├── security.py          # Middleware API Key
├── services/
│   └── diagnostico.py   # Lógica de diagnóstico por PPPoE
├── clients/             # Integraciones externas
│   ├── smartolt.py      # API SmartOLT
│   ├── ispcube.py       # API ISPCube
│   └── mikrotik.py      # API RouterOS Mikrotik
├── db/
│   └── sqlite.py        # Clase Database, esquema y queries
├── sync.py              # Proceso de sincronización nocturna
└── utils/
    └── safe_call.py     # Wrapper defensivo para llamadas externas
```

---

## 4. Definición de Archivos Fuente

### `main.py`
- FastAPI con endpoints:
  - `/diagnosis/{pppoe_user}` → devuelve diagnóstico completo.  
  - `/health` → chequeo de estado.  
- Middleware de API Key (`X-API-Key`).  
- CORS habilitado para frontend.  

### `config.py`
- Carga variables desde `.env`.  
- Define rutas (`DB_PATH`, `SMARTOLT_BASEURL`, etc.).  
- Configura logging centralizado en `data/logs/sync.log`.  

### `security.py`
- Middleware para validar API Key.  
- Devuelve `401 unauthorized` si la clave no coincide.  

### `services/diagnostico.py`
- Función `consultar_diagnostico(pppoe_user)`:
  - Consulta base local (`db.get_diagnosis`).  
  - Valida PPPoE en Mikrotik.  
  - Consulta estado, señales y VLANs en SmartOLT.  
  - Integra datos de ISPCube.  

### `clients/smartolt.py`
- Funciones para interactuar con SmartOLT:
  - `get_all_onus()` → listado completo de ONUs.  
  - `get_onu_status(id)` → estado de ONU.  
  - `get_onu_signals(id)` → señales ópticas.  
  - `get_attached_vlans(id)` → VLANs asociadas.  

### `clients/ispcube.py`
- Autenticación vía token.  
- Funciones:
  - `obtener_nodos()` → lista de nodos.  
  - `obtener_todas_conexiones()` → conexiones PPPoE.  
  - `obtener_planes()` → planes de servicio.  
  - `obtener_clientes()` → clientes completos.  

### `clients/mikrotik.py`
- Conexión a RouterOS vía `routeros_api`.  
- Funciones:
  - `obtener_secret(router_ip, pppoe_user, puerto)` → busca secret PPPoE.  
  - `validar_pppoe(router_ip, pppoe_user, puerto)` → chequea si está activo.  
- Comentados: crear, borrar y migrar secrets.  

### `db/sqlite.py`
- Clase `Database` con métodos `insert_*` para cada tabla.  
- `get_diagnosis(pppoe_user)` → query principal de diagnóstico.  
- `init_db()` → crea esquema de tablas (`subscribers`, `nodes`, `plans`, `connections`, `clientes`, `sync_status`).  

### `sync.py`
- Funciones de sincronización:
  - `sync_onus()`, `sync_nodes()`, `sync_plans()`, `sync_connections()`, `sync_clientes()`.  
- `nightly_sync()` → ejecuta todo el proceso y actualiza relaciones PPPoE ↔ node_id ↔ connection_id.  

---

## 5. Flujo de Diagnóstico
1. **Frontend** llama a `/diagnosis/{pppoe_user}`.  
2. **Backend** consulta DB local (`get_diagnosis`).  
3. **Mikrotik** valida PPPoE activo/inactivo.  
4. **SmartOLT** devuelve estado, señales y VLANs.  
5. **ISPCube** aporta datos de cliente, plan y nodo.  
6. Respuesta JSON consolidada para el operador.  

---

## 6. Flujo de Sincronización Nocturna
1. `cron` ejecuta `python sync.py`.  
2. Se inicializa DB (`init_db`).  
3. Se descargan datos de SmartOLT, ISPCube.  
4. Se insertan en tablas locales.  
5. Se actualizan relaciones (`match_connections`).  
6. Se registra estado en `sync_status`.  

---

## 7. ADRs relevantes
- **ADR-001**: Uso de SQLite como base inicial.  
- **ADR-002**: Deploy con git hooks + sudoers NOPASSWD.  
- **ADR-003**: Separación modular (mappers, helpers, DB).  
- **ADR-004**: Roadmap migración a PostgreSQL.  

---

## 8. Roadmap Backend
- Migrar DB a PostgreSQL.  
- Integrar cnMaestro para clientes wireless.  
- Extender diagnóstico con alarmas GenieACS.  
- Automatizar tests en deploy.  

