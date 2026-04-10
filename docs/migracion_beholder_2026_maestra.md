# Migracion Beholder 2026 - Guia Maestra

## 1. Objetivo

Este documento consolida, en formato operativo, todo lo implementado y validado en Beholder durante esta sesion de trabajo 2026 para replicarlo en otro entorno (incluyendo variantes con PostgreSQL) sin romper comportamiento productivo.

El objetivo de la migracion es:
- Replicar endpoints, contratos HTTP y comportamiento funcional.
- Replicar resiliencia, performance y observabilidad.
- Adaptar exclusivamente la capa de persistencia cuando el destino no usa SQLite.

## 2. Alcance funcional implementado

Se implemento y valido la linea de trabajo Oraculo 2.0 para trafico PPPoE con IP dinamica:

- Router aislado con prefijo dedicado:
  - `/api/v1/oraculo`

- Endpoints funcionales:
  - `GET /api/v1/oraculo/trafico/{ip_cliente}`
  - `GET /api/v1/oraculo/sesiones/{usuario_pppoe}`
  - `GET /api/v1/oraculo/trafico-pppoe/{usuario_pppoe}`
  - `GET /api/v1/oraculo/debug`

- Logica de negocio clave:
  - Resolucion de sesiones PPPoE desde Graylog.
  - Extraccion de IP de sesion desde mensaje de logs.
  - Normalizacion y merge de segmentos temporales por IP.
  - Consulta de trafico por segmento en Influx.
  - Merge de puntos por timestamp.
  - Fallback a bucket raw cuando resumen no devuelve puntos.

- Resiliencia:
  - Retry + backoff para Graylog e Influx en errores transitorios.
  - Tolerancia a respuesta Graylog JSON/CSV.
  - Manejo robusto de errores SmartOLT para evitar `dict has no attribute json`.

- Performance:
  - Consultas por segmentos en paralelo (`asyncio.gather`).
  - Concurrencia acotada por semaforo configurable.
  - Cache TTL de sesiones Graylog para requests repetidos.

- Observabilidad:
  - Linea estructurada por request en endpoint PPPoE:
    - usuario, rango, status, cache hit/miss, cantidad segmentos, tiempos parciales y total, puntos resultantes.

## 3. Resumen tecnico de `oraculo_router.py`

Resumen pensado para inyectar en otra instancia de la app sin tener que reconstruir el analisis.

### 3.1 Dependencias nuevas

- `influxdb-client` para ejecutar consultas Flux contra InfluxDB v2.
- `requests` para las consultas HTTP a Graylog.
- `asyncio`, `time`, `csv`, `io`, `re` y `datetime` para orquestacion, normalizacion y parseo.
- `pydantic` para los modelos de respuesta del router.

### 3.2 Estructura de los nuevos endpoints

- `GET /api/v1/oraculo/trafico/{ip_cliente}`
  - Devuelve trafico historico o realtime por IP fija.

- `GET /api/v1/oraculo/sesiones/{usuario_pppoe}`
  - Devuelve historial de sesiones PPPoE derivado de Graylog.

- `GET /api/v1/oraculo/trafico-pppoe/{usuario_pppoe}`
  - Resuelve sesiones PPPoE + IP dinamica + Influx por segmentos.

- `GET /api/v1/oraculo/debug`
  - Probe simple de Influx y Graylog para diagnostico operativo.

### 3.3 Logica de collage de segmentos PPPoE

- Busca eventos login/logout en Graylog dentro de una ventana amplia.
- Extrae la IP cliente desde el mensaje de log.
- Convierte cada sesion en un segmento `inicio/fin`.
- Clampa cada segmento al rango solicitado.
- Ordena y fusiona segmentos solapados o contiguos por IP.
- Lanza consultas en Influx por segmento y luego mergea los puntos por timestamp.
- Si el bucket resumido no devuelve datos, cae a consulta raw para no perder cobertura.

### 3.4 Funciones asincronas de Influx y Graylog

- `_get_cached_graylog_sessions(...)`
  - Cache TTL para sesiones Graylog.
  - Evita repetir consultas costosas en requests cercanos.

- `_query_influx_interval_async(...)`
  - Wrapper asincrono para ejecutar consultas Influx en paralelo con semaforo.

- `_build_pppoe_traffic_series(...)`
  - Coordina cache Graylog, normalizacion de segmentos y fan-out a Influx.

- `obtener_trafico_pppoe(...)`
  - Expone el endpoint y registra metricas estructuradas por request.

### 3.5 Formato resumido para reutilizacion rapida

Este bloque puede copiarse casi literal a otra sesion:

> `oraculo_router.py` implementa un router FastAPI aislado que resuelve trafico PPPoE dinamico. Usa Graylog para reconstruir sesiones login/logout, normaliza segmentos por IP y rango, consulta Influx en paralelo por segmento con concurrencia acotada y cache TTL, y fusiona resultados en una serie temporal unica. Incluye fallback de bucket resumido a raw, endpoint de debug, y logging estructurado por request. Depende de `influxdb-client`, `requests`, `asyncio`, `datetime`, `csv`, `io` y `re`.

## 3. Archivos impactados

Implementacion principal:
- [app/oraculo_router.py](app/oraculo_router.py)
- [app/config.py](app/config.py)
- [app/clients/smartolt.py](app/clients/smartolt.py)
- [app/services/diagnostico.py](app/services/diagnostico.py)
- [app/jobs/sync.py](app/jobs/sync.py)
- [app/main.py](app/main.py)
- [requirements.txt](requirements.txt)

Documentacion:
- [docs/api_trafico_pppoe.md](docs/api_trafico_pppoe.md)
- [README-esp.md](README-esp.md) (actualizacion funcional)
- [config/.env.example](config/.env.example) (actualizacion de variables)

## 4. Variables de entorno introducidas o relevantes

Integracion Influx/Graylog/Oraculo:

- ORACULO_INFLUX_URL
- ORACULO_INFLUX_TOKEN
- ORACULO_INFLUX_ORG
- ORACULO_INFLUX_BUCKET
- ORACULO_INFLUX_RAW_BUCKET
- ORACULO_INFLUX_RESUMEN_BUCKET
- ORACULO_INFLUX_RAW_MEASUREMENT
- ORACULO_INFLUX_RESUMEN_MEASUREMENT
- ORACULO_INFLUX_IN_BYTES_FIELD
- ORACULO_INFLUX_RESUMEN_IP_TAG
- ORACULO_INFLUX_NODE_TAG
- ORACULO_INFLUX_RESUMEN_SENTIDO_TAG
- ORACULO_INFLUX_SENTIDO_DESCARGA
- ORACULO_INFLUX_SENTIDO_SUBIDA
- ORACULO_INFLUX_REALTIME_WINDOW_SECONDS
- ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS
- ORACULO_INFLUX_TIMEOUT_MS
- ORACULO_INFLUX_MAX_CONCURRENCY
- ORACULO_NODO_IP_MAP

Resiliencia:
- ORACULO_RETRY_ATTEMPTS
- ORACULO_RETRY_BACKOFF_SEC
- ORACULO_RETRY_BACKOFF_MULTIPLIER

Graylog:
- ORACULO_GRAYLOG_URL
- ORACULO_GRAYLOG_USER
- ORACULO_GRAYLOG_PASSWORD
- ORACULO_GRAYLOG_TIMEOUT_SEC
- ORACULO_GRAYLOG_RANGE_SEC
- ORACULO_GRAYLOG_SORT
- ORACULO_GRAYLOG_FIELDS
- ORACULO_GRAYLOG_SESSION_CACHE_TTL_SEC

Generales:
- API_KEY
- SMARTOLT_BASEURL
- SMARTOLT_TOKEN
- MK_HOST / MK_PORT
- DB_PATH

## 5. Dependencias requeridas

Dependencias minimas verificadas:

- fastapi==0.115.0
- uvicorn[standard]==0.30.0
- requests==2.32.3
- python-dotenv==1.0.1
- RouterOS-api==0.21.0
- influxdb-client==1.46.0

Nota critica de produccion:
- Si falta `influxdb-client`, el servicio falla al arrancar por `ModuleNotFoundError: No module named 'influxdb_client'`.

## 6. Contrato funcional que NO debe romperse

- Seguridad:
  - Header `x-api-key` obligatorio por middleware.

- Contratos de salida:
  - `trafico-pppoe` devuelve lista de puntos `{tiempo, descarga_mbps, subida_mbps}`.
  - Sin datos: lista vacia `[]`, no error 500.

- SmartOLT degradado:
  - Ante timeout/HTTP error/DNS error, diagnostico no debe romper con excepcion de parseo.
  - Debe devolver payload de error controlado (dict) o lista vacia segun funcion.

- Sync robusto:
  - `get_all_onus()` debe devolver lista siempre (incluido en error -> `[]`) para evitar fallos por tipo inesperado.

## 7. Estrategia de migracion al entorno con PostgreSQL

Regla principal: replicar logica y contratos, cambiar solo persistencia.

### 7.1 Capa de persistencia

Si destino usa PostgreSQL, crear adaptador equivalente a `Database` con las mismas firmas usadas por servicios:
- `get_diagnosis(pppoe_user)`
- `search_client(q)`
- `get_router_for_pppoe(pppoe_user)`
- `get_nodes_for_sync()`
- `insert_*`, `match_connections()`, `commit()`, `close()`

### 7.2 Reglas de compatibilidad

- Mantener nombres de campos esperados por servicios (`nodo_ip`, `unique_external_id`, etc.).
- Mantener retornos dict/list y semantica de errores.
- No alterar rutas ni payloads HTTP.

### 7.3 Roadmap sugerido de aplicacion

- Portar config + variables de entorno.
- Portar router Oraculo completo.
- Portar cliente SmartOLT robusto.
- Portar diagnostico y sync.
- Adaptar DB a PostgreSQL sin tocar contratos.
- Ejecutar smoke tests.
- Habilitar en produccion con rollout gradual.

## 8. Pruebas ejecutadas/validadas en esta implementacion

- Conectividad SmartOLT post-cambio de URL:
  - `get_all_onus()` retorno valido (miles de ONUs).


- Diagnostico extremo a extremo:
  - Sin `AttributeError` por `.json()` en objeto dict.
  - `onu_status_smrt` y `onu_signal_smrt` con retorno controlado dict.
  - `onu_vlan` con retorno controlado list.


- Endpoints Oraculo:
  - Consultas por rango con respuesta 200 en usuarios reales.
  - Comportamiento estable con sesiones dinamicas.


- Produccion:
  - Correccion de incidente por dependencia faltante (`influxdb-client`) en `requirements.txt`.

## 9. Incidentes y fixes aplicados

- DNS/transport errors contra SmartOLT:
  - Antes: rompian parseo por uso de `.json()` sobre dict.
  - Fix: manejo consistente de tipos y payload de error.


- Faltante de dependencia Influx en produccion:
  - Fix: agregar `influxdb-client==1.46.0` a `requirements.txt`.


- Error de conexion frontend `ERR_CONNECTION_REFUSED`:
  - Diagnostico: backend caido/no escuchando puerto, no problema de Nginx.
  - Regla: reiniciar servicio app; recargar Nginx solo si cambio de config Nginx.

## 10. Checklist de despliegue seguro

- Pull de codigo.
- Instalar deps del venv:
  - `python -m pip install -r requirements.txt`
- Reiniciar servicio de app.
- Verificar estado con systemd/journal.
- Verificar `GET /health` local.
- Verificar endpoint critico `trafico-pppoe` y `diagnosis`.
- Validar logs de aplicacion y ausencia de tracebacks.

## 11. Rollback

Si hay regresion:

- Revertir commit de aplicacion problematico.
- Reinstalar requirements del commit estable.
- Reiniciar servicio.
- Validar health y endpoints.

## 12. Commits de referencia en esta etapa

- 525c4d0 (base de integracion Oraculo y mejoras previas de esta linea de trabajo)
- 2656fb0 (robustez SmartOLT, elimina `dict has no attribute json`)
- 5b96f35 (agrega `influxdb-client` a requirements)

## 13. Entregable para otra sesion de Copilot

Usar este documento junto con:
- `docs/migracion_beholder_2026_codigo_anexos.md`

Orden recomendado para la otra sesion:

- Aplicar codigo fuente anexo por modulo.
- Adaptar solo capa DB a PostgreSQL.
- Ejecutar checklist de pruebas funcionales.
- Confirmar observabilidad y resiliencia.
