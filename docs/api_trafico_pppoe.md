# API Tráfico PPPoE

## Objetivo
Esta API entrega la serie temporal de consumo para un usuario PPPoE, lista para graficar en frontend.

La lógica de backend ya resuelve internamente:
- IPs dinámicas del usuario dentro del rango solicitado.
- Sesiones temporales (login/logout) y consolidación por ventana.
- Merge de puntos de tráfico en una sola serie cronológica.

El frontend solo debe consultar por usuario y rango, y graficar los puntos recibidos.

---

## Endpoint

- Metodo: `GET`
- URL: `/api/v1/oraculo/trafico-pppoe/{usuario_pppoe}`

### Headers requeridos
- `x-api-key: <API_KEY>`
- `Content-Type: application/json` (opcional para GET)

Ejemplo:

```bash
curl -X GET "http://127.0.0.1:8500/api/v1/oraculo/trafico-pppoe/ecruz?rango=24h" \
  -H "x-api-key: TU_API_KEY"
```

---

## Parametros

### Path params
- `usuario_pppoe` (string, requerido)
  - Usuario PPPoE del cliente.
  - Ejemplo: `ecruz`

### Query params
- `rango` (string, opcional)
  - Default: `24h`
  - Valores permitidos:
    - `15m`
    - `30m`
    - `60m`
    - `12h`
    - `24h`
    - `7d`
    - `30d`

---

## Respuesta exitosa (200)

La respuesta es un arreglo de puntos ordenados por tiempo ascendente.

```json
[
  {
    "tiempo": "2026-04-09T23:03:00+00:00",
    "descarga_mbps": 12.4375,
    "subida_mbps": 1.2084
  },
  {
    "tiempo": "2026-04-09T23:08:00+00:00",
    "descarga_mbps": 10.9941,
    "subida_mbps": 0.9822
  },
  {
    "tiempo": "2026-04-09T23:13:00+00:00",
    "descarga_mbps": 14.2218,
    "subida_mbps": 1.4437
  }
]
```

### Campos
- `tiempo`: timestamp ISO-8601 UTC.
- `descarga_mbps`: trafico de descarga en Mbps.
- `subida_mbps`: trafico de subida en Mbps.

Nota: los calculos en bytes/ventanas se hacen en backend; frontend consume directamente Mbps para graficar.

---

## Errores

Formato de error estandar FastAPI:

```json
{
  "detail": "Mensaje de error"
}
```

### 404 Not Found
Casos tipicos:
- Ruta incorrecta.
- Prefijo de API incorrecto.

Ejemplo:

```json
{
  "detail": "Not Found"
}
```

### 500 Internal Server Error
Casos tipicos:
- Configuracion incompleta de integraciones.
- Error inesperado no controlado en backend.

Ejemplo:

```json
{
  "detail": "Internal Server Error"
}
```

### Otros codigos que pueden aparecer
- `400`: rango no soportado.
- `401`: API key invalida o ausente.
- `502`: falla al consultar servicios externos (Graylog/InfluxDB).

---

## Recomendaciones frontend

- Graficar con `tiempo` en eje X y `descarga_mbps`/`subida_mbps` en eje Y.
- Permitir selector de rango con los valores soportados.
- Si la respuesta es `[]`, mostrar estado sin datos en vez de error.
- Reintentar en `502` con backoff corto (por ejemplo 1-2 reintentos).
