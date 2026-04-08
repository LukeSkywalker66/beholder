import asyncio
import csv
import io
import re
import time
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


class ProbeResult(BaseModel):
    ok: bool
    time_sec: float
    detail: str


class OraculoDebugResponse(BaseModel):
    influx: ProbeResult
    graylog: ProbeResult


class SesionIpCliente(BaseModel):
    inicio: str
    fin: str
    ip_cliente: Optional[str] = None
    router: str
    razon_desconexion: Optional[str] = None


_REALTIME_RANGES = {"15m", "30m", "60m"}
_HISTORY_RANGES = {"12h", "24h", "7d", "30d"}
_RANGE_SECONDS = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "60m": 60 * 60,
    "12h": 12 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "timed out",
        "timeout",
        "connection refused",
        "failed to establish a new connection",
        "max retries exceeded",
        "temporarily unavailable",
        "connection reset",
    )
    return any(marker in text for marker in markers)


def _sleep_with_backoff(attempt: int) -> None:
    base = max(config.ORACULO_RETRY_BACKOFF_SEC, 0.0)
    multiplier = max(config.ORACULO_RETRY_BACKOFF_MULTIPLIER, 1.0)
    delay = base * (multiplier ** max(attempt - 1, 0))
    if delay > 0:
        time.sleep(delay)


def _extract_ipv4_candidates(message_text: str) -> list[str]:
    ipv4_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    candidates = re.findall(ipv4_pattern, message_text)
    cleaned: list[str] = []
    for candidate in candidates:
        parts = candidate.split(".")
        if all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            cleaned.append(candidate)
    return cleaned


def _extract_session_ip(message_text: str) -> Optional[str]:
    text = message_text.lower()
    direct_patterns = (
        r"(?:assigned|asignada|asignado|ip)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})",
        r"(?:address|cliente|client)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})",
        r"(?:ip_cliente|ip cliente)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})",
    )

    for pattern in direct_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    candidates = _extract_ipv4_candidates(message_text)
    if not candidates:
        return None

    # Prefer the first non-obvious router IP when multiple addresses appear in the message.
    for candidate in candidates:
        if candidate != config.MK_HOST:
            return candidate
    return candidates[0]


def _merge_traffic_points(points: list[TraficoPunto]) -> list[TraficoPunto]:
    merged: dict[str, TraficoPunto] = {}
    for point in points:
        current = merged.get(point.tiempo)
        if current is None:
            merged[point.tiempo] = point
            continue

        merged[point.tiempo] = TraficoPunto(
            tiempo=point.tiempo,
            descarga_mbps=round(current.descarga_mbps + point.descarga_mbps, 4),
            subida_mbps=round(current.subida_mbps + point.subida_mbps, 4),
        )

    return [merged[key] for key in sorted(merged.keys())]


def _build_influx_interval_query(
    ip_cliente: str,
    rango: str,
    start_iso: str,
    stop_iso: str,
) -> str:
    raw_bucket = config.ORACULO_INFLUX_RAW_BUCKET
    resumen_bucket = config.ORACULO_INFLUX_RESUMEN_BUCKET
    raw_measurement = config.ORACULO_INFLUX_RAW_MEASUREMENT
    resumen_measurement = config.ORACULO_INFLUX_RESUMEN_MEASUREMENT
    in_bytes_field = config.ORACULO_INFLUX_IN_BYTES_FIELD
    resumen_ip_tag = config.ORACULO_INFLUX_RESUMEN_IP_TAG
    sentido_tag = config.ORACULO_INFLUX_RESUMEN_SENTIDO_TAG
    sentido_descarga = config.ORACULO_INFLUX_SENTIDO_DESCARGA
    sentido_subida = config.ORACULO_INFLUX_SENTIDO_SUBIDA
    realtime_window_seconds = config.ORACULO_INFLUX_REALTIME_WINDOW_SECONDS
    resumen_window_seconds = config.ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS

    if rango in _REALTIME_RANGES:
        return f'''
ip = "{ip_cliente}"

descarga = from(bucket: "{raw_bucket}")
    |> range(start: time(v: "{start_iso}"), stop: time(v: "{stop_iso}"))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["dst"] == ip)
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "{sentido_tag}", value: "{sentido_descarga}")

subida = from(bucket: "{raw_bucket}")
    |> range(start: time(v: "{start_iso}"), stop: time(v: "{stop_iso}"))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["src"] == ip)
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "{sentido_tag}", value: "{sentido_subida}")

union(tables: [descarga, subida])
    |> pivot(rowKey:["_time"], columnKey: ["{sentido_tag}"], valueColumn: "_value")
    |> map(fn: (r) => ({{
    r with descarga_mbps: float(v: r["{sentido_descarga}"]) * 8.0 / {realtime_window_seconds}.0 / 1024.0 / 1024.0,
    subida_mbps: float(v: r["{sentido_subida}"]) * 8.0 / {realtime_window_seconds}.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

    if rango in _HISTORY_RANGES:
        return f'''
from(bucket: "{resumen_bucket}")
    |> range(start: time(v: "{start_iso}"), stop: time(v: "{stop_iso}"))
    |> filter(fn: (r) => r["_measurement"] == "{resumen_measurement}" and r["_field"] == "{in_bytes_field}" and r["{resumen_ip_tag}"] == "{ip_cliente}")
    |> pivot(rowKey:["_time"], columnKey: ["{sentido_tag}"], valueColumn: "_value")
    |> map(fn: (r) => ({{
        r with descarga_mbps: float(v: r["{sentido_descarga}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0,
        subida_mbps: float(v: r["{sentido_subida}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

    raise HTTPException(status_code=400, detail=f"Rango no soportado: {rango}")


def _query_influx_interval(ip_cliente: str, rango: str, start_iso: str, stop_iso: str) -> list[TraficoPunto]:
    influx_url = config.ORACULO_INFLUX_URL
    influx_token = config.ORACULO_INFLUX_TOKEN
    influx_org = config.ORACULO_INFLUX_ORG
    timeout_ms = config.ORACULO_INFLUX_TIMEOUT_MS

    flux_query = _build_influx_interval_query(ip_cliente, rango, start_iso, stop_iso)

    attempts = max(config.ORACULO_RETRY_ATTEMPTS, 1)
    last_exc: Optional[Exception] = None
    tables = []
    for attempt in range(1, attempts + 1):
        try:
            with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=timeout_ms) as client:
                tables = client.query_api().query(query=flux_query, org=influx_org)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            should_retry = attempt < attempts and _is_transient_error(exc)
            if should_retry:
                _sleep_with_backoff(attempt)
                continue
            raise HTTPException(status_code=502, detail=f"Fallo consultando InfluxDB: {exc}") from exc

    if last_exc is not None:
        raise HTTPException(status_code=502, detail=f"Fallo consultando InfluxDB: {last_exc}") from last_exc

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


def _query_graylog_session_windows(usuario_pppoe: str, limite: int, range_sec: Optional[int] = None) -> list[SesionIpCliente]:
    raw_messages = _query_graylog_raw(usuario_pppoe, limite, range_sec=range_sec)
    eventos: list[dict] = []

    for envelope in raw_messages:
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
        ip_cliente = _extract_session_ip(text)

        eventos.append(
            {
                "inicio": timestamp.isoformat(),
                "ip_cliente": ip_cliente,
                "router": str(router),
                "razon_desconexion": _extract_disconnect_reason(text),
                "is_login": is_login,
                "is_logout": is_logout,
            }
        )

    eventos.sort(key=lambda e: e["inicio"])

    sesiones: list[SesionIpCliente] = []
    current_login: Optional[dict] = None
    for ev in eventos:
        if current_login is None:
            if ev.get("is_login"):
                current_login = ev
            continue

        if ev.get("is_logout"):
            current_login["fin"] = ev["inicio"]
            sesiones.append(
                SesionIpCliente(
                    inicio=current_login["inicio"],
                    fin=current_login.get("fin", ev["inicio"]),
                    ip_cliente=current_login.get("ip_cliente"),
                    router=current_login.get("router", "Desconocido"),
                    razon_desconexion=ev.get("razon_desconexion"),
                )
            )
            current_login = None
            continue

        if ev.get("is_login"):
            current_login = ev

    if current_login is not None:
        sesiones.append(
            SesionIpCliente(
                inicio=current_login["inicio"],
                fin=datetime.now(timezone.utc).isoformat(),
                ip_cliente=current_login.get("ip_cliente"),
                router=current_login.get("router", "Desconocido"),
                razon_desconexion=current_login.get("razon_desconexion"),
            )
        )

    return sesiones[:limite]


def _build_pppoe_traffic_series(usuario_pppoe: str, rango: str, limite: int = 100) -> list[TraficoPunto]:
    ventanas = _query_graylog_session_windows(usuario_pppoe, limite, range_sec=_RANGE_SECONDS.get(rango))
    if not ventanas:
        return []

    merged_points: list[TraficoPunto] = []
    for ventana in ventanas:
        if not ventana.ip_cliente:
            continue

        start_iso = ventana.inicio
        stop_iso = ventana.fin if ventana.fin else datetime.now(timezone.utc).isoformat()
        merged_points.extend(_query_influx_interval(ventana.ip_cliente, rango, start_iso, stop_iso))

    return _merge_traffic_points(merged_points)


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
    resumen_ip_tag = config.ORACULO_INFLUX_RESUMEN_IP_TAG
    sentido_tag = config.ORACULO_INFLUX_RESUMEN_SENTIDO_TAG
    sentido_descarga = config.ORACULO_INFLUX_SENTIDO_DESCARGA
    sentido_subida = config.ORACULO_INFLUX_SENTIDO_SUBIDA
    realtime_window_seconds = config.ORACULO_INFLUX_REALTIME_WINDOW_SECONDS
    resumen_window_seconds = config.ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS

    if rango in _REALTIME_RANGES:
        return f'''
ip = "{ip_cliente}"
rango = "-{rango}"

descarga = from(bucket: "{raw_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["dst"] == ip)
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "{sentido_tag}", value: "{sentido_descarga}")

subida = from(bucket: "{raw_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["src"] == ip)
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "{sentido_tag}", value: "{sentido_subida}")

union(tables: [descarga, subida])
    |> pivot(rowKey:["_time"], columnKey: ["{sentido_tag}"], valueColumn: "_value")
    |> map(fn: (r) => ({{
    r with descarga_mbps: float(v: r["{sentido_descarga}"]) * 8.0 / {realtime_window_seconds}.0 / 1024.0 / 1024.0,
    subida_mbps: float(v: r["{sentido_subida}"]) * 8.0 / {realtime_window_seconds}.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

    if rango in _HISTORY_RANGES:
        return f'''
rango = "-{rango}"

from(bucket: "{resumen_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{resumen_measurement}" and r["_field"] == "{in_bytes_field}" and r["{resumen_ip_tag}"] == "{ip_cliente}")
    |> pivot(rowKey:["_time"], columnKey: ["{sentido_tag}"], valueColumn: "_value")
    |> map(fn: (r) => ({{
        r with descarga_mbps: float(v: r["{sentido_descarga}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0,
        subida_mbps: float(v: r["{sentido_subida}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0
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

    attempts = max(config.ORACULO_RETRY_ATTEMPTS, 1)
    last_exc: Optional[Exception] = None
    tables = []
    for attempt in range(1, attempts + 1):
        try:
            with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=timeout_ms) as client:
                tables = client.query_api().query(query=flux_query, org=influx_org)
            last_exc = None
            break
        except HTTPException:
            raise
        except Exception as exc:
            last_exc = exc
            should_retry = attempt < attempts and _is_transient_error(exc)
            if should_retry:
                config.logger.warning(
                    "[ORACULO][INFLUX] Retry %s/%s ip=%s rango=%s motivo=%s",
                    attempt,
                    attempts,
                    ip_cliente,
                    rango,
                    str(exc)[:180],
                )
                _sleep_with_backoff(attempt)
                continue

            config.logger.exception(
                "[ORACULO][INFLUX] Fallo consulta ip=%s rango=%s url=%s org=%s timeout_ms=%s",
                ip_cliente,
                rango,
                influx_url,
                influx_org,
                timeout_ms,
            )
            raise HTTPException(status_code=502, detail=f"Fallo consultando InfluxDB: {exc}") from exc

    if last_exc is not None:
        raise HTTPException(status_code=502, detail=f"Fallo consultando InfluxDB: {last_exc}") from last_exc

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


def _query_graylog_raw(usuario_pppoe: str, limite: int, range_sec: Optional[int] = None) -> list[dict]:
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
        "range": range_sec if range_sec is not None else config.ORACULO_GRAYLOG_RANGE_SEC,
        "limit": fetch_limit,
        "sort": config.ORACULO_GRAYLOG_SORT,
        "fields": config.ORACULO_GRAYLOG_FIELDS,
    }

    attempts = max(config.ORACULO_RETRY_ATTEMPTS, 1)
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                endpoint,
                params=params,
                auth=(graylog_user, graylog_password),
                headers={"X-Requested-By": "beholder-oraculo", "Accept": "application/json"},
                timeout=timeout_sec,
            )
            response.raise_for_status()

            content_type = (response.headers.get("Content-Type") or "").lower()
            body = response.text or ""
            if "application/json" in content_type:
                if not body.strip():
                    return []
                payload = response.json()
                return payload.get("messages", [])

            if "text/csv" in content_type:
                if not body.strip():
                    return []

                records: list[dict] = []
                reader = csv.DictReader(io.StringIO(body))
                for row in reader:
                    records.append(
                        {
                            "message": {
                                "timestamp": row.get("timestamp"),
                                "source": row.get("source") or row.get("gl2_remote_ip"),
                                "message": row.get("message", ""),
                            }
                        }
                    )
                return records

            if not body.strip():
                return []

            raise HTTPException(
                status_code=502,
                detail=f"Formato de respuesta Graylog no soportado: {content_type or 'desconocido'}",
            )
        except HTTPException:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            retry_status = None
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                retry_status = exc.response.status_code

            should_retry = attempt < attempts and (
                _is_transient_error(exc)
                or retry_status in (429, 500, 502, 503, 504)
            )
            if should_retry:
                config.logger.warning(
                    "[ORACULO][GRAYLOG] Retry %s/%s usuario=%s motivo=%s",
                    attempt,
                    attempts,
                    usuario_pppoe,
                    str(exc)[:180],
                )
                _sleep_with_backoff(attempt)
                continue

            config.logger.exception(
                "[ORACULO][GRAYLOG] Fallo HTTP usuario=%s limite=%s endpoint=%s timeout_sec=%s",
                usuario_pppoe,
                limite,
                endpoint,
                timeout_sec,
            )
            raise HTTPException(status_code=502, detail=f"Fallo consultando Graylog: {exc}") from exc
        except ValueError as exc:
            last_exc = exc
            should_retry = attempt < attempts and _is_transient_error(exc)
            if should_retry:
                _sleep_with_backoff(attempt)
                continue

            config.logger.exception(
                "[ORACULO][GRAYLOG] JSON invalido usuario=%s endpoint=%s",
                usuario_pppoe,
                endpoint,
            )
            raise HTTPException(status_code=502, detail=f"Respuesta invalida de Graylog: {exc}") from exc

    if last_exc is not None:
        raise HTTPException(status_code=502, detail=f"Fallo consultando Graylog: {last_exc}") from last_exc
    return []


def _probe_influx() -> ProbeResult:
    start = time.perf_counter()
    influx_url = config.ORACULO_INFLUX_URL
    influx_token = config.ORACULO_INFLUX_TOKEN
    influx_org = config.ORACULO_INFLUX_ORG
    if not influx_url or not influx_token or not influx_org:
        return ProbeResult(ok=False, time_sec=round(time.perf_counter() - start, 3), detail="Credenciales incompletas")

    try:
        with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=config.ORACULO_INFLUX_TIMEOUT_MS) as client:
            bucket = client.buckets_api().find_bucket_by_name(config.ORACULO_INFLUX_RESUMEN_BUCKET)
            if not bucket:
                return ProbeResult(
                    ok=False,
                    time_sec=round(time.perf_counter() - start, 3),
                    detail=f"Bucket no visible: {config.ORACULO_INFLUX_RESUMEN_BUCKET}",
                )
    except Exception as exc:
        return ProbeResult(ok=False, time_sec=round(time.perf_counter() - start, 3), detail=str(exc)[:200])

    return ProbeResult(ok=True, time_sec=round(time.perf_counter() - start, 3), detail="OK")


def _probe_graylog() -> ProbeResult:
    start = time.perf_counter()
    graylog_url = config.ORACULO_GRAYLOG_URL
    graylog_user = config.ORACULO_GRAYLOG_USER
    graylog_password = config.ORACULO_GRAYLOG_PASSWORD
    if not graylog_url or not graylog_user or not graylog_password:
        return ProbeResult(ok=False, time_sec=round(time.perf_counter() - start, 3), detail="Credenciales incompletas")

    endpoint = f"{graylog_url.rstrip('/')}/api/search/universal/relative"
    try:
        response = requests.get(
            endpoint,
            params={
                "query": "*",
                "range": 300,
                "limit": 1,
                "sort": config.ORACULO_GRAYLOG_SORT,
                "fields": config.ORACULO_GRAYLOG_FIELDS,
            },
            auth=(graylog_user, graylog_password),
            headers={"X-Requested-By": "beholder-oraculo"},
            timeout=config.ORACULO_GRAYLOG_TIMEOUT_SEC,
        )
        if response.status_code >= 400:
            return ProbeResult(
                ok=False,
                time_sec=round(time.perf_counter() - start, 3),
                detail=f"HTTP {response.status_code}",
            )
    except Exception as exc:
        return ProbeResult(ok=False, time_sec=round(time.perf_counter() - start, 3), detail=str(exc)[:200])

    return ProbeResult(ok=True, time_sec=round(time.perf_counter() - start, 3), detail="OK")


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


@router.get("/trafico-pppoe/{usuario_pppoe}", response_model=list[TraficoPunto])
async def obtener_trafico_pppoe(
    usuario_pppoe: str,
    rango: Literal["15m", "30m", "60m", "12h", "24h", "7d", "30d"] = Query(default="24h"),
) -> list[TraficoPunto]:
    return await asyncio.to_thread(_build_pppoe_traffic_series, usuario_pppoe, rango)


@router.get("/debug", response_model=OraculoDebugResponse)
async def debug_oraculo() -> OraculoDebugResponse:
    influx = await asyncio.to_thread(_probe_influx)
    graylog = await asyncio.to_thread(_probe_graylog)
    return OraculoDebugResponse(influx=influx, graylog=graylog)
