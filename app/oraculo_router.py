import asyncio
import re
from datetime import datetime, timezone
from typing import Literal, Optional

import requests
from fastapi import APIRouter, HTTPException, Query
from influxdb_client.client.influxdb_client import InfluxDBClient
from pydantic import BaseModel
from app import config


router = APIRouter(prefix="/api/v1/oraculo", tags=["oraculo"])


class TraficoPunto(BaseModel):
    tiempo: str
    descarga_mbps: float
    subida_mbps: float


class SesionCliente(BaseModel):
    inicio: str
    fin: str
    duracion: str
    razon_desconexion: Optional[str] = None
    router: str


_REALTIME_RANGES = {"15m", "30m", "60m"}
_HISTORY_RANGES = {"12h", "24h", "7d", "30d"}


def _format_duration(start: datetime, end: datetime) -> str:
    total_seconds = int(max((end - start).total_seconds(), 0))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return f"{days} d {hours} h {minutes} min"
    if hours > 0:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def _extract_disconnect_reason(message_text: str) -> Optional[str]:
    reason_match = re.search(r"(?:reason|razon|motivo)\s*[:=]\s*(.+)$", message_text, re.IGNORECASE)
    if reason_match:
        return reason_match.group(1).strip()

    out_match = re.search(r"logged out\s*,\s*(.+)$", message_text, re.IGNORECASE)
    if out_match:
        possible_reason = out_match.group(1).strip()
        if possible_reason and "user" not in possible_reason.lower():
            return possible_reason

    discon_match = re.search(r"disconnected\s*,\s*(.+)$", message_text, re.IGNORECASE)
    if discon_match:
        return discon_match.group(1).strip()

    return None


def _parse_graylog_timestamp(raw_timestamp: str) -> datetime:
    # Graylog usually returns ISO8601 with trailing Z; normalize for Python parser.
    normalized = raw_timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_flux_query(ip_cliente: str, rango: str) -> str:
        raw_bucket = config.ORACULO_INFLUX_RAW_BUCKET
        resumen_bucket = config.ORACULO_INFLUX_RESUMEN_BUCKET
        raw_measurement = config.ORACULO_INFLUX_RAW_MEASUREMENT
        resumen_measurement = config.ORACULO_INFLUX_RESUMEN_MEASUREMENT
        in_bytes_field = config.ORACULO_INFLUX_IN_BYTES_FIELD

        if rango in _REALTIME_RANGES:
                return f'''
ip = "{ip_cliente}"
rango = "-{rango}"

descarga = from(bucket: "{raw_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["dst"] == ip)
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "sentido", value: "descarga")

subida = from(bucket: "{raw_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["src"] == ip)
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "sentido", value: "subida")

union(tables: [descarga, subida])
    |> pivot(rowKey:["_time"], columnKey: ["sentido"], valueColumn: "_value")
    |> map(fn: (r) => ({{
            r with descarga_mbps: float(v: r.descarga) * 8.0 / 60.0 / 1024.0 / 1024.0,
            subida_mbps: float(v: r.subida) * 8.0 / 60.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

        if rango in _HISTORY_RANGES:
                return f'''
rango = "-{rango}"

from(bucket: "{resumen_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{resumen_measurement}" and r["ip_cliente"] == "{ip_cliente}")
    |> pivot(rowKey:["_time"], columnKey: ["sentido"], valueColumn: "_value")
    |> map(fn: (r) => ({{
            r with descarga_mbps: float(v: r.descarga) * 8.0 / 300.0 / 1024.0 / 1024.0,
            subida_mbps: float(v: r.subida) * 8.0 / 300.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

        raise HTTPException(status_code=400, detail=f"Rango no soportado: {rango}")


def _query_influx_trafico(ip_cliente: str, rango: str) -> list[TraficoPunto]:
    influx_url = config.ORACULO_INFLUX_URL
    influx_token = config.ORACULO_INFLUX_TOKEN
    influx_org = config.ORACULO_INFLUX_ORG
    timeout_ms = config.ORACULO_INFLUX_TIMEOUT_MS

    if not influx_url or not influx_token or not influx_org:
        config.logger.error(
            "[ORACULO][INFLUX] Credenciales incompletas url=%s org=%s raw_bucket=%s resumen_bucket=%s",
            bool(influx_url),
            bool(influx_org),
            config.ORACULO_INFLUX_RAW_BUCKET,
            config.ORACULO_INFLUX_RESUMEN_BUCKET,
        )
        raise HTTPException(status_code=500, detail="Credenciales de InfluxDB incompletas")

    flux_query = _build_flux_query(ip_cliente, rango)

    try:
        with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=timeout_ms) as client:
            tables = client.query_api().query(query=flux_query, org=influx_org)
    except HTTPException:
        raise
    except Exception as exc:
        config.logger.exception(
            "[ORACULO][INFLUX] Fallo consulta ip=%s rango=%s url=%s org=%s timeout_ms=%s",
            ip_cliente,
            rango,
            influx_url,
            influx_org,
            timeout_ms,
        )
        raise HTTPException(status_code=502, detail=f"Fallo consultando InfluxDB: {exc}") from exc

    puntos: list[TraficoPunto] = []
    for table in tables:
        for record in table.records:
            timestamp = record.get_time()
            if timestamp is None:
                continue

            descarga_raw = record.values.get("descarga_mbps")
            subida_raw = record.values.get("subida_mbps")
            descarga = float(descarga_raw) if descarga_raw is not None else 0.0
            subida = float(subida_raw) if subida_raw is not None else 0.0

            puntos.append(
                TraficoPunto(
                    tiempo=timestamp.isoformat(),
                    descarga_mbps=round(descarga, 4),
                    subida_mbps=round(subida, 4),
                )
            )

    return puntos


def _query_graylog_raw(usuario_pppoe: str, limite: int) -> list[dict]:
    graylog_url = config.ORACULO_GRAYLOG_URL
    graylog_user = config.ORACULO_GRAYLOG_USER
    graylog_password = config.ORACULO_GRAYLOG_PASSWORD
    timeout_sec = config.ORACULO_GRAYLOG_TIMEOUT_SEC

    if not graylog_url or not graylog_user or not graylog_password:
        config.logger.error(
            "[ORACULO][GRAYLOG] Credenciales incompletas url=%s user=%s password=%s",
            bool(graylog_url),
            bool(graylog_user),
            bool(graylog_password),
        )
        raise HTTPException(status_code=500, detail="Credenciales de Graylog incompletas")

    base_url = graylog_url.rstrip("/")
    endpoint = f"{base_url}/api/search/universal/relative"

    fetch_limit = min(max(limite * 8, 200), 5000)
    params = {
        "query": f'"{usuario_pppoe}"',
        "range": 30 * 24 * 60 * 60,
        "limit": fetch_limit,
        "sort": "asc",
    }

    try:
        response = requests.get(
            endpoint,
            params=params,
            auth=(graylog_user, graylog_password),
            headers={"X-Requested-By": "beholder-oraculo"},
            timeout=timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
    except HTTPException:
        raise
    except requests.RequestException as exc:
        config.logger.exception(
            "[ORACULO][GRAYLOG] Fallo HTTP usuario=%s limite=%s endpoint=%s timeout_sec=%s",
            usuario_pppoe,
            limite,
            endpoint,
            timeout_sec,
        )
        raise HTTPException(status_code=502, detail=f"Fallo consultando Graylog: {exc}") from exc
    except ValueError as exc:
        config.logger.exception(
            "[ORACULO][GRAYLOG] JSON invalido usuario=%s endpoint=%s",
            usuario_pppoe,
            endpoint,
        )
        raise HTTPException(status_code=502, detail=f"Respuesta invalida de Graylog: {exc}") from exc

    return payload.get("messages", [])


def _pair_sessions(usuario_pppoe: str, graylog_messages: list[dict], limite: int) -> list[SesionCliente]:
    eventos: list[dict] = []

    for envelope in graylog_messages:
        msg = envelope.get("message", {})
        text = str(msg.get("message", ""))
        if not text:
            continue

        lower_text = text.lower()
        if usuario_pppoe.lower() not in lower_text:
            continue

        is_login = "logged in" in lower_text
        is_logout = any(key in lower_text for key in ("logged out", "disconnected", "logout"))

        if not is_login and not is_logout:
            continue

        timestamp_raw = msg.get("timestamp")
        if not timestamp_raw:
            continue

        try:
            timestamp = _parse_graylog_timestamp(str(timestamp_raw))
        except Exception:
            continue

        router = (
            msg.get("source")
            or msg.get("router")
            or msg.get("device_name")
            or msg.get("gl2_remote_ip")
            or "Desconocido"
        )

        eventos.append(
            {
                "ts": timestamp,
                "is_login": is_login,
                "is_logout": is_logout,
                "reason": _extract_disconnect_reason(text),
                "router": str(router),
            }
        )

    eventos.sort(key=lambda e: e["ts"])

    sesiones: list[SesionCliente] = []
    logins_abiertos: list[dict] = []
    now = datetime.now(timezone.utc)

    for ev in eventos:
        if ev["is_login"]:
            logins_abiertos.append(ev)
            continue

        if ev["is_logout"]:
            if not logins_abiertos:
                # Ignoramos logout sin login previo visible en la ventana consultada.
                continue

            inicio_ev = logins_abiertos.pop(0)
            inicio_ts = inicio_ev["ts"]
            fin_ts = ev["ts"]

            sesiones.append(
                SesionCliente(
                    inicio=inicio_ts.isoformat(),
                    fin=fin_ts.isoformat(),
                    duracion=_format_duration(inicio_ts, fin_ts),
                    razon_desconexion=ev.get("reason"),
                    router=ev.get("router") or inicio_ev.get("router") or "Desconocido",
                )
            )

    for inicio_ev in logins_abiertos:
        inicio_ts = inicio_ev["ts"]
        sesiones.append(
            SesionCliente(
                inicio=inicio_ts.isoformat(),
                fin="Activa",
                duracion=_format_duration(inicio_ts, now),
                razon_desconexion=None,
                router=inicio_ev.get("router") or "Desconocido",
            )
        )

    sesiones.sort(key=lambda s: s.inicio, reverse=True)
    return sesiones[:limite]


@router.get("/trafico/{ip_cliente}", response_model=list[TraficoPunto])
async def obtener_trafico_cliente(
    ip_cliente: str,
    rango: Literal["15m", "30m", "60m", "12h", "24h", "7d", "30d"] = Query(default="24h"),
) -> list[TraficoPunto]:
    return await asyncio.to_thread(_query_influx_trafico, ip_cliente, rango)


@router.get("/sesiones/{usuario_pppoe}", response_model=list[SesionCliente])
async def obtener_historial_sesiones(
    usuario_pppoe: str,
    limite: int = Query(default=20, ge=1, le=200),
) -> list[SesionCliente]:
    mensajes = await asyncio.to_thread(_query_graylog_raw, usuario_pppoe, limite)
    return _pair_sessions(usuario_pppoe, mensajes, limite)
