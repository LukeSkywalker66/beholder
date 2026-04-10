# Migracion Beholder 2026 - Codigo Anexos Completos

Este documento incluye fuentes completos de los modulos criticos para replicacion en otra base de codigo.

Uso recomendado:
1. Copiar modulo por modulo.
2. Ajustar solo persistencia (PostgreSQL) y wiring particular del nuevo entorno.
3. Mantener contratos HTTP, nombres de campos y manejo de errores.

---

## A. app/oraculo_router.py (fuente completo)

```python
import asyncio
import csv
import io
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import requests
from fastapi import APIRouter, HTTPException, Query
from influxdb_client.client.influxdb_client import InfluxDBClient
from pydantic import BaseModel
from app import config
from app.db.sqlite import Database


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

_GRAYLOG_SESSION_CACHE: dict[str, tuple[float, list[SesionIpCliente]]] = {}
_GRAYLOG_SESSION_CACHE_LOCK = asyncio.Lock()
_REQUEST_LOGGER = logging.getLogger("uvicorn.error")


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


def _resolve_influx_node_ip(router_ip: Optional[str]) -> Optional[str]:
    if not router_ip:
        return None

    router_ip = router_ip.strip()
    if not router_ip:
        return None

    return config.ORACULO_NODO_IP_MAP.get(router_ip, router_ip)


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
    nodo_ip: Optional[str] = None,
    force_raw: bool = False,
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
    node_tag = config.ORACULO_INFLUX_NODE_TAG
    realtime_window_seconds = config.ORACULO_INFLUX_REALTIME_WINDOW_SECONDS
    resumen_window_seconds = config.ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS
    node_clause = f' and r["{node_tag}"] == "{nodo_ip}"' if node_tag and nodo_ip else ""

    if force_raw or rango in _REALTIME_RANGES:
        return f'''
ip = "{ip_cliente}"

descarga = from(bucket: "{raw_bucket}")
    |> range(start: time(v: "{start_iso}"), stop: time(v: "{stop_iso}"))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["dst"] == ip{node_clause})
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "{sentido_tag}", value: "{sentido_descarga}")

subida = from(bucket: "{raw_bucket}")
    |> range(start: time(v: "{start_iso}"), stop: time(v: "{stop_iso}"))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["src"] == ip{node_clause})
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
    |> filter(fn: (r) => r["_measurement"] == "{resumen_measurement}" and r["_field"] == "{in_bytes_field}" and r["{resumen_ip_tag}"] == "{ip_cliente}"{node_clause})
    |> pivot(rowKey:["_time"], columnKey: ["{sentido_tag}"], valueColumn: "_value")
    |> map(fn: (r) => ({{
        r with descarga_mbps: float(v: r["{sentido_descarga}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0,
        subida_mbps: float(v: r["{sentido_subida}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

    raise HTTPException(status_code=400, detail=f"Rango no soportado: {rango}")


def _query_influx_interval(
    ip_cliente: str,
    rango: str,
    start_iso: str,
    stop_iso: str,
    nodo_ip: Optional[str] = None,
) -> list[TraficoPunto]:
    influx_url = config.ORACULO_INFLUX_URL
    influx_token = config.ORACULO_INFLUX_TOKEN
    influx_org = config.ORACULO_INFLUX_ORG
    timeout_ms = config.ORACULO_INFLUX_TIMEOUT_MS

    flux_query = _build_influx_interval_query(ip_cliente, rango, start_iso, stop_iso, nodo_ip=nodo_ip)

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

    if not puntos and rango in _HISTORY_RANGES:
        config.logger.info(
            "[ORACULO][INFLUX] Fallback a crudo usuario/ip=%s rango=%s nodo=%s",
            ip_cliente,
            rango,
            nodo_ip or "<sin nodo>",
        )
        fallback_query = _build_influx_interval_query(
            ip_cliente,
            rango,
            start_iso,
            stop_iso,
            nodo_ip=nodo_ip,
            force_raw=True,
        )

        try:
            with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=timeout_ms) as client:
                fallback_tables = client.query_api().query(query=fallback_query, org=influx_org)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Fallo consultando InfluxDB: {exc}") from exc

        for table in fallback_tables:
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


def _to_utc_datetime(raw_iso: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
    except Exception:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_pppoe_segments(
    sesiones: list[SesionIpCliente],
    rango_segundos: int,
) -> list[tuple[str, str, str]]:
    now = datetime.now(timezone.utc)
    rango_segundos = max(rango_segundos, 1)
    window_start = now - timedelta(seconds=rango_segundos)
    window_end = now

    prepared: list[tuple[str, datetime, datetime]] = []
    for sesion in sesiones:
        if not sesion.ip_cliente:
            continue

        start_dt = _to_utc_datetime(sesion.inicio)
        if not start_dt:
            continue

        end_dt = _to_utc_datetime(sesion.fin) if sesion.fin else None
        if not end_dt:
            end_dt = now

        if end_dt <= start_dt:
            continue

        clamped_start = max(start_dt, window_start)
        clamped_end = min(end_dt, window_end)
        if clamped_end <= clamped_start:
            continue

        prepared.append((sesion.ip_cliente.strip(), clamped_start, clamped_end))

    if not prepared:
        return []

    prepared.sort(key=lambda row: (row[0], row[1], row[2]))
    merged: list[tuple[str, datetime, datetime]] = []
    for ip, start_dt, end_dt in prepared:
        if not merged:
            merged.append((ip, start_dt, end_dt))
            continue

        prev_ip, prev_start, prev_end = merged[-1]
        if ip == prev_ip and start_dt <= prev_end:
            merged[-1] = (prev_ip, prev_start, max(prev_end, end_dt))
            continue

        merged.append((ip, start_dt, end_dt))

    return [(ip, start.isoformat(), end.isoformat()) for ip, start, end in merged]


async def _get_cached_graylog_sessions(
    usuario_pppoe: str,
    limite: int,
    range_sec: int,
) -> tuple[list[SesionIpCliente], str]:
    cache_key = f"{usuario_pppoe.strip().lower()}|{limite}|{range_sec}"
    ttl_sec = max(config.ORACULO_GRAYLOG_SESSION_CACHE_TTL_SEC, 0)
    now_mono = time.monotonic()

    if ttl_sec == 0:
        sesiones = await asyncio.to_thread(_query_graylog_session_windows, usuario_pppoe, limite, range_sec)
        return sesiones, "bypass"

    if ttl_sec > 0:
        async with _GRAYLOG_SESSION_CACHE_LOCK:
            cached = _GRAYLOG_SESSION_CACHE.get(cache_key)
            if cached:
                created_at, sesiones = cached
                if now_mono - created_at <= ttl_sec:
                    return list(sesiones), "hit"
                _GRAYLOG_SESSION_CACHE.pop(cache_key, None)

    sesiones = await asyncio.to_thread(_query_graylog_session_windows, usuario_pppoe, limite, range_sec)

    async with _GRAYLOG_SESSION_CACHE_LOCK:
        _GRAYLOG_SESSION_CACHE[cache_key] = (time.monotonic(), list(sesiones))

    return sesiones, "miss"


async def _query_influx_interval_async(
    sem: asyncio.Semaphore,
    ip_cliente: str,
    rango: str,
    start_iso: str,
    stop_iso: str,
    nodo_ip: Optional[str],
) -> list[TraficoPunto]:
    async with sem:
        return await asyncio.to_thread(
            _query_influx_interval,
            ip_cliente,
            rango,
            start_iso,
            stop_iso,
            nodo_ip,
        )


def _resolve_pppoe_node_context(usuario_pppoe: str) -> tuple[Optional[str], Optional[str]]:
    db = Database()
    try:
        diagnosis = db.get_diagnosis(usuario_pppoe)
    except Exception as exc:
        config.logger.warning(
            "[ORACULO][NODO] No se pudo resolver nodo para %s: %s",
            usuario_pppoe,
            str(exc)[:180],
        )
        return None, None
    finally:
        db.close()

    nodo_ip = diagnosis.get("nodo_ip")
    nodo_influx_ip = _resolve_influx_node_ip(str(nodo_ip)) if nodo_ip else None
    return (str(nodo_ip) if nodo_ip else None, nodo_influx_ip)


async def _build_pppoe_traffic_series(
    usuario_pppoe: str,
    rango: str,
    limite: int = 100,
) -> tuple[list[TraficoPunto], dict[str, str | int | float]]:
    metrics: dict[str, str | int | float] = {
        "cache": "unknown",
        "segments": 0,
        "graylog_sec": 0.0,
        "influx_sec": 0.0,
    }

    nodo_origen_ip, nodo_influx_ip = _resolve_pppoe_node_context(usuario_pppoe)
    if nodo_origen_ip:
        config.logger.info(
            "[ORACULO][NODO] usuario=%s nodo_db=%s nodo_influx=%s",
            usuario_pppoe,
            nodo_origen_ip,
            nodo_influx_ip or "<sin mapeo>",
        )

    rango_segundos = _RANGE_SECONDS.get(rango, 0)
    graylog_range_sec = max(rango_segundos, config.ORACULO_GRAYLOG_RANGE_SEC)
    graylog_t0 = time.perf_counter()
    sesiones, cache_status = await _get_cached_graylog_sessions(usuario_pppoe, limite, graylog_range_sec)
    graylog_dt = time.perf_counter() - graylog_t0
    metrics["cache"] = cache_status
    metrics["graylog_sec"] = round(graylog_dt, 3)

    segmentos = _normalize_pppoe_segments(sesiones, rango_segundos)
    metrics["segments"] = len(segmentos)
    if not segmentos:
        return [], metrics

    max_concurrency = max(config.ORACULO_INFLUX_MAX_CONCURRENCY, 1)
    sem = asyncio.Semaphore(max_concurrency)

    tasks = [
        _query_influx_interval_async(sem, ip_cliente, rango, start_iso, stop_iso, nodo_influx_ip)
        for ip_cliente, start_iso, stop_iso in segmentos
    ]

    influx_t0 = time.perf_counter()
    batches = await asyncio.gather(*tasks)
    influx_dt = time.perf_counter() - influx_t0
    metrics["influx_sec"] = round(influx_dt, 3)

    merged_points: list[TraficoPunto] = []
    for batch in batches:
        merged_points.extend(batch)

    return _merge_traffic_points(merged_points), metrics


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


def _build_flux_query(ip_cliente: str, rango: str, nodo_ip: Optional[str] = None) -> str:
    raw_bucket = config.ORACULO_INFLUX_RAW_BUCKET
    resumen_bucket = config.ORACULO_INFLUX_RESUMEN_BUCKET
    raw_measurement = config.ORACULO_INFLUX_RAW_MEASUREMENT
    resumen_measurement = config.ORACULO_INFLUX_RESUMEN_MEASUREMENT
    in_bytes_field = config.ORACULO_INFLUX_IN_BYTES_FIELD
    resumen_ip_tag = config.ORACULO_INFLUX_RESUMEN_IP_TAG
    sentido_tag = config.ORACULO_INFLUX_RESUMEN_SENTIDO_TAG
    sentido_descarga = config.ORACULO_INFLUX_SENTIDO_DESCARGA
    sentido_subida = config.ORACULO_INFLUX_SENTIDO_SUBIDA
    node_tag = config.ORACULO_INFLUX_NODE_TAG
    realtime_window_seconds = config.ORACULO_INFLUX_REALTIME_WINDOW_SECONDS
    resumen_window_seconds = config.ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS
    node_clause = f' and r["{node_tag}"] == "{nodo_ip}"' if node_tag and nodo_ip else ""

    if rango in _REALTIME_RANGES:
        return f'''
ip = "{ip_cliente}"
rango = "-{rango}"

descarga = from(bucket: "{raw_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["dst"] == ip{node_clause})
    |> keep(columns: ["_time", "_value"])
    |> aggregateWindow(every: 1m, fn: sum, createEmpty: false)
    |> set(key: "{sentido_tag}", value: "{sentido_descarga}")

subida = from(bucket: "{raw_bucket}")
    |> range(start: duration(v: rango))
    |> filter(fn: (r) => r["_measurement"] == "{raw_measurement}" and r["_field"] == "{in_bytes_field}" and r["src"] == ip{node_clause})
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
    |> filter(fn: (r) => r["_measurement"] == "{resumen_measurement}" and r["_field"] == "{in_bytes_field}" and r["{resumen_ip_tag}"] == "{ip_cliente}"{node_clause})
    |> pivot(rowKey:["_time"], columnKey: ["{sentido_tag}"], valueColumn: "_value")
    |> map(fn: (r) => ({{
        r with descarga_mbps: float(v: r["{sentido_descarga}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0,
        subida_mbps: float(v: r["{sentido_subida}"]) * 8.0 / {resumen_window_seconds}.0 / 1024.0 / 1024.0
    }}))
    |> keep(columns: ["_time", "descarga_mbps", "subida_mbps"])
    |> sort(columns: ["_time"], desc: false)
'''

    raise HTTPException(status_code=400, detail=f"Rango no soportado: {rango}")


def _query_influx_trafico(ip_cliente: str, rango: str, nodo_ip: Optional[str] = None) -> list[TraficoPunto]:
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

    flux_query = _build_flux_query(ip_cliente, rango, nodo_ip=nodo_ip)

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
    total_t0 = time.perf_counter()
    status_code = 200
    points_count = 0
    metrics: dict[str, str | int | float] = {
        "cache": "unknown",
        "segments": 0,
        "graylog_sec": 0.0,
        "influx_sec": 0.0,
    }
    error_text = ""

    try:
        puntos, metrics = await _build_pppoe_traffic_series(usuario_pppoe, rango)
        points_count = len(puntos)
        return puntos
    except HTTPException as exc:
        status_code = exc.status_code
        error_text = str(exc.detail)
        raise
    except Exception as exc:
        status_code = 500
        error_text = str(exc)
        raise
    finally:
        total_sec = round(time.perf_counter() - total_t0, 3)
        _REQUEST_LOGGER.info(
            "oraculo_pppoe_metrics user=%s rango=%s status=%s cache=%s segments=%s graylog_sec=%s influx_sec=%s total_sec=%s points=%s error=%s",
            usuario_pppoe,
            rango,
            status_code,
            metrics.get("cache", "unknown"),
            metrics.get("segments", 0),
            metrics.get("graylog_sec", 0.0),
            metrics.get("influx_sec", 0.0),
            total_sec,
            points_count,
            error_text[:180] if error_text else "-",
        )


@router.get("/debug", response_model=OraculoDebugResponse)
async def debug_oraculo() -> OraculoDebugResponse:
    influx = await asyncio.to_thread(_probe_influx)
    graylog = await asyncio.to_thread(_probe_graylog)
    return OraculoDebugResponse(influx=influx, graylog=graylog)
```

---

## B. app/config.py (fuente completo)

```python
import os
import logging
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join("config", ".env"))


def _parse_mapping_env(raw_value: str | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not raw_value:
        return mapping

    for chunk in raw_value.replace("\n", ";").split(";"):
        item = chunk.strip()
        if not item or "=" not in item:
            continue

        source_ip, target_ip = item.split("=", 1)
        source_ip = source_ip.strip()
        target_ip = target_ip.strip()
        if source_ip and target_ip:
            mapping[source_ip] = target_ip

    return mapping

# Variables de entorno
API_KEY = os.getenv("API_KEY")
SMARTOLT_BASEURL = os.getenv("SMARTOLT_BASEURL")
SMARTOLT_TOKEN = os.getenv("SMARTOLT_TOKEN")
MK_HOST = os.getenv("MK_HOST")
MK_USER = os.getenv("MK_USER")
MK_PASS = os.getenv("MK_PASS")
MK_PORT = int(os.getenv("MK_PORT", 8799))
GENIEACS_URL = os.getenv("GENIEACS_URL")
ISPCUBE_BASEURL=os.getenv("ISPCUBE_BASEURL")
ISPCUBE_APIKEY=os.getenv("ISPCUBE_APIKEY")
ISPCUBE_USER=os.getenv("ISPCUBE_USER")
ISPCUBE_PASSWORD=os.getenv("ISPCUBE_PASSWORD")
ISPCUBE_CLIENTID=os.getenv("ISPCUBE_CLIENTID")

# Oráculo - InfluxDB
ORACULO_INFLUX_URL = os.getenv("ORACULO_INFLUX_URL") or os.getenv("INFLUXDB_URL")
ORACULO_INFLUX_TOKEN = os.getenv("ORACULO_INFLUX_TOKEN") or os.getenv("INFLUXDB_TOKEN")
ORACULO_INFLUX_ORG = os.getenv("ORACULO_INFLUX_ORG") or os.getenv("INFLUXDB_ORG")
ORACULO_INFLUX_BUCKET = os.getenv("ORACULO_INFLUX_BUCKET") or os.getenv("INFLUXDB_BUCKET", "netflow")
ORACULO_INFLUX_RAW_BUCKET = os.getenv("ORACULO_INFLUX_RAW_BUCKET", ORACULO_INFLUX_BUCKET)
ORACULO_INFLUX_RESUMEN_BUCKET = os.getenv("ORACULO_INFLUX_RESUMEN_BUCKET", "netflow_resumen")
ORACULO_INFLUX_RAW_MEASUREMENT = os.getenv("ORACULO_INFLUX_RAW_MEASUREMENT", "netflow")
ORACULO_INFLUX_RESUMEN_MEASUREMENT = os.getenv("ORACULO_INFLUX_RESUMEN_MEASUREMENT", "resumen_5m")
ORACULO_INFLUX_IN_BYTES_FIELD = os.getenv("ORACULO_INFLUX_IN_BYTES_FIELD", "in_bytes")
ORACULO_INFLUX_RESUMEN_IP_TAG = os.getenv("ORACULO_INFLUX_RESUMEN_IP_TAG", "ip_cliente")
ORACULO_INFLUX_NODE_TAG = os.getenv("ORACULO_INFLUX_NODE_TAG", "source")
ORACULO_INFLUX_RESUMEN_SENTIDO_TAG = os.getenv("ORACULO_INFLUX_RESUMEN_SENTIDO_TAG", "sentido")
ORACULO_INFLUX_SENTIDO_DESCARGA = os.getenv("ORACULO_INFLUX_SENTIDO_DESCARGA", "descarga")
ORACULO_INFLUX_SENTIDO_SUBIDA = os.getenv("ORACULO_INFLUX_SENTIDO_SUBIDA", "subida")
ORACULO_INFLUX_REALTIME_WINDOW_SECONDS = int(os.getenv("ORACULO_INFLUX_REALTIME_WINDOW_SECONDS", "60"))
ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS = int(os.getenv("ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS", "300"))
ORACULO_INFLUX_TIMEOUT_MS = int(os.getenv("ORACULO_INFLUX_TIMEOUT_MS", "10000"))
ORACULO_INFLUX_MAX_CONCURRENCY = int(os.getenv("ORACULO_INFLUX_MAX_CONCURRENCY", "6"))
ORACULO_NODO_IP_MAP = _parse_mapping_env(os.getenv("ORACULO_NODO_IP_MAP") or os.getenv("ORACULO_NODE_IP_MAP"))
ORACULO_RETRY_ATTEMPTS = int(os.getenv("ORACULO_RETRY_ATTEMPTS", "3"))
ORACULO_RETRY_BACKOFF_SEC = float(os.getenv("ORACULO_RETRY_BACKOFF_SEC", "1.0"))
ORACULO_RETRY_BACKOFF_MULTIPLIER = float(os.getenv("ORACULO_RETRY_BACKOFF_MULTIPLIER", "2.0"))

# Oráculo - Graylog
ORACULO_GRAYLOG_URL = os.getenv("ORACULO_GRAYLOG_URL") or os.getenv("GRAYLOG_URL")
ORACULO_GRAYLOG_USER = (
    os.getenv("ORACULO_GRAYLOG_USER")
    or os.getenv("GRAYLOG_USER")
    or os.getenv("GRAYLOG_USERNAME")
    or os.getenv("GRAYLOG_TOKEN")
)
ORACULO_GRAYLOG_PASSWORD = (
    os.getenv("ORACULO_GRAYLOG_PASSWORD")
    or os.getenv("GRAYLOG_PASSWORD")
    or os.getenv("GRAYLOG_PASS")
)
if ORACULO_GRAYLOG_USER and not ORACULO_GRAYLOG_PASSWORD:
    # Graylog token auth commonly uses username=<token> and password='token'.
    ORACULO_GRAYLOG_PASSWORD = "token"
ORACULO_GRAYLOG_TIMEOUT_SEC = int(os.getenv("ORACULO_GRAYLOG_TIMEOUT_SEC", "15"))
ORACULO_GRAYLOG_RANGE_SEC = int(os.getenv("ORACULO_GRAYLOG_RANGE_SEC", str(30 * 24 * 60 * 60)))
ORACULO_GRAYLOG_SESSION_CACHE_TTL_SEC = int(os.getenv("ORACULO_GRAYLOG_SESSION_CACHE_TTL_SEC", "60"))
ORACULO_GRAYLOG_SORT = os.getenv("ORACULO_GRAYLOG_SORT", "timestamp:asc")
ORACULO_GRAYLOG_FIELDS = os.getenv("ORACULO_GRAYLOG_FIELDS", "message,source,timestamp")

DB_PATH = os.path.abspath(os.getenv("DB_PATH", "data/diag.db"))

# Crear carpeta data/ si no existe
db_dir = os.path.dirname(DB_PATH)
if not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# Logging centralizado
log_dir = os.path.join(db_dir, "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(log_dir, "sync.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("beholder")
```

---

## C. app/clients/smartolt.py (fuente completo)

```python
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
```

---

## D. app/services/diagnostico.py (fuente completo)

```python
from app.db.sqlite import Database
from app.clients import mikrotik, smartolt, ispcube
from app.config import logger
from app import config # Importar config para fallback

def consultar_diagnostico(pppoe_user: str) -> dict:
    db = Database()
    try:
        # Esto ahora busca en ISPCube primero, luego en SmartOLT
        base = db.get_diagnosis(pppoe_user)
        if "error" in base:
            return base

        diagnosis = base.copy()

        # Mikrotik
        # Si no tenemos nodo_ip (cliente solo en OLT), usamos el default MK_HOST del .env
        router_ip = base.get("nodo_ip")
        if not router_ip:
            logger.warning(f"Sin IP de nodo para {pppoe_user}. Usando MK_HOST por defecto.")
            router_ip = config.MK_HOST

        # Validamos PPPoE (si router_ip es válido)
        if router_ip:
            pppoe_info = mikrotik.validar_pppoe(router_ip, pppoe_user, base.get("puerto", config.MK_PORT))
            diagnosis["mikrotik"] = pppoe_info
        else:
             diagnosis["mikrotik"] = {"active": False, "error": "No Router IP"}

        # SmartOLT (Solo si tenemos unique_external_id)
        external_id = base.get("unique_external_id")
        if external_id:
            diagnosis["onu_status_smrt"] = smartolt.get_onu_status(external_id)
            diagnosis["onu_signal_smrt"] = smartolt.get_onu_signals(external_id)
            diagnosis["onu_vlan"] = smartolt.get_attached_vlans(external_id)
        else:
             # Caso raro: Cliente en ISPCube pero sin ONU vinculada
             diagnosis["onu_status_smrt"] = {"status": False, "error": "Sin ONU asociada"}

        return diagnosis
    except Exception as e:
        logger.exception(f"Error en diagnóstico de {pppoe_user}. Detalles: {e}")
        return diagnosis # Retornamos lo que tengamos
    finally:
        db.close()
```

---

## E. app/jobs/sync.py (fuente completo)

```python
from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

def sync_nodes(db):
    print("   ↳ Buscando Nodos en ISPCube...", end=" ", flush=True)
    try:
        nodes = ispcube.obtener_nodos()
        if nodes:
            db.cursor.execute("DELETE FROM nodes")
            for n in nodes:
                db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
            config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")
            db.log_sync_status("ispcube", "ok", f"{len(nodes)} nodos sincronizados")
            print(f"✅ ({len(nodes)} encontrados)")
        else:
            print("⚠️ Lista vacía")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error Nodos: {e}")

def sync_secrets(db):
    nodes = db.get_nodes_for_sync()
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos para sync secrets.")
        return

    db.cursor.execute("DELETE FROM ppp_secrets")
    print(f"   ↳ Consultando {len(nodes)} Mikrotiks:")
    total_secrets = 0

    for node in nodes:
        ip = node["ip"]
        name = node["name"]
        port = node["port"] if node["port"] else config.MK_PORT
        print(f"      > {name} ({ip})...", end=" ", flush=True)
        
        try:
            secrets = mikrotik.get_all_secrets(ip, port)
            if secrets is not None:
                for s in secrets:
                    db.insert_secret(s, ip)
                count = len(secrets)
                total_secrets += count
                print(f"✅ ({count})")
            else:
                print("⚠️ Sin respuesta")
        except Exception as e:
            print(f"❌ Error: {e}")
            config.logger.error(f"[SYNC] Error en router {ip}: {e}")
    
    db.commit()
    config.logger.info(f"[SYNC] {total_secrets} secrets sincronizados.")
    print(f"   ↳ Resumen: {total_secrets} secrets guardados.")

def sync_onus(db):
    print("   ↳ Consultando SmartOLT...", end=" ", flush=True)
    try:
        onus = smartolt.get_all_onus()
        if onus:
            db.cursor.execute("DELETE FROM subscribers")
            for onu in onus:
                db.insert_subscriber(
                    onu.get("unique_external_id"), onu.get("sn"), onu.get("olt_name"), 
                    onu.get("olt_id"), onu.get("board"), onu.get("port"), onu.get("onu"), 
                    onu.get("onu_type_id"), onu.get("name"), onu.get("mode")
                )
            db.log_sync_status("smartolt", "ok", f"{len(onus)} ONUs sincronizadas")
            config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
            print(f"✅ ({len(onus)} ONUs)")
        else:
            print("⚠️ Sin datos")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error SmartOLT: {e}")

def sync_plans(db):
    print("   ↳ [ISPCube] Bajando Planes...", end=" ", flush=True)
    try:
        planes = ispcube.obtener_planes()
        if planes:
            db.cursor.execute("DELETE FROM plans")
            for p in planes:
                db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
            config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")
            print(f"✅ ({len(planes)})")
        else: print("⚠️")
    except Exception as e: print(f"❌ {e}")

def sync_connections(db):
    print("   ↳ [ISPCube] Bajando Conexiones (Lista Completa)...", end=" ", flush=True)
    try:
        # VOLVEMOS AL MÉTODO CLÁSICO
        conexiones = ispcube.obtener_todas_conexiones()
        if conexiones:
            db.cursor.execute("DELETE FROM connections")
            for c in conexiones:
                if not c.get("id") or not c.get("user"): continue
                db.insert_connection(
                    str(c["id"]), str(c["user"]), str(c["customer_id"]), 
                    str(c["node_id"]), str(c["plan_id"]), c.get("direccion")
                )
            config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")
            db.log_sync_status("ispcube", "ok", f"{len(conexiones)} conexiones sincronizadas")
            print(f"✅ ({len(conexiones)})")
        else:
            print("⚠️ Vacío")
    except Exception as e:
        print(f"❌ {e}")
        config.logger.error(f"[SYNC] Error Connections: {e}")

def sync_clientes(db):
    print("   ↳ [ISPCube] Bajando Clientes...", end=" ", flush=True)
    try:
        clientes = ispcube.obtener_clientes()
        if clientes:
            db.cursor.execute("DELETE FROM clientes")
            db.cursor.execute("DELETE FROM clientes_emails")
            db.cursor.execute("DELETE FROM clientes_telefonos")

            for c in clientes:
                db.insert_cliente(mapear_cliente(c))
                insertar_contactos_relacionados(db, c)

            db.commit()
            config.logger.info(f"[SYNC] {len(clientes)} clientes sincronizados.")
            db.log_sync_status("ispcube", "ok", f"{len(clientes)} clientes sincronizados")
            print(f"✅ ({len(clientes)})")
        else:
            print("⚠️ Vacío")
    except Exception as e:
        print(f"❌ {e}")

# --- UTILIDADES ---
def insertar_contactos_relacionados(db, json_cliente: dict):
    for email_obj in json_cliente.get("contact_emails", []):
        if email_obj.get("email"):
            db.insert_cliente_email(json_cliente["id"], email_obj.get("email"))
    for tel_obj in json_cliente.get("phones", []):
        if tel_obj.get("number"):
            db.insert_cliente_telefono(json_cliente["id"], tel_obj.get("number"))

def mapear_cliente(json_cliente: dict) -> dict:
    return {
        "id": json_cliente.get("id"),
        "code": json_cliente.get("code"),
        "name": json_cliente.get("name"),
        "tax_residence": json_cliente.get("tax_residence"),
        "type": json_cliente.get("type"),
        "tax_situation_id": json_cliente.get("tax_situation_id"),
        "identification_type_id": json_cliente.get("identification_type_id"),
        "doc_number": json_cliente.get("doc_number"),
        "auto_bill_sending": json_cliente.get("auto_bill_sending"),
        "auto_payment_recipe_sending": json_cliente.get("auto_payment_recipe_sending"),
        "nickname": json_cliente.get("nickname"),
        "comercial_activity": json_cliente.get("comercial_activity"),
        "address": json_cliente.get("address"),
        "between_address1": json_cliente.get("between_address1"),
        "between_address2": json_cliente.get("between_address2"),
        "city_id": json_cliente.get("city_id"),
        "lat": json_cliente.get("lat"),
        "lng": json_cliente.get("lng"),
        "extra1": json_cliente.get("extra1"),
        "extra2": json_cliente.get("extra2"),
        "entity_id": json_cliente.get("entity_id"),
        "collector_id": json_cliente.get("collector_id"),
        "seller_id": json_cliente.get("seller_id"),
        "block": json_cliente.get("block"),
        "free": json_cliente.get("free"),
        "apply_late_payment_due": json_cliente.get("apply_late_payment_due"),
        "apply_reconnection": json_cliente.get("apply_reconnection"),
        "contract": json_cliente.get("contract"),
        "contract_type_id": json_cliente.get("contract_type_id"),
        "contract_expiration_date": json_cliente.get("contract_expiration_date"),
        "paycomm": json_cliente.get("paycomm"),
        "expiration_type_id": json_cliente.get("expiration_type_id"),
        "business_id": json_cliente.get("business_id"),
        "first_expiration_date": json_cliente.get("first_expiration_date"),
        "second_expiration_date": json_cliente.get("second_expiration_date"),
        "next_month_corresponding_date": json_cliente.get("next_month_corresponding_date"),
        "start_date": json_cliente.get("start_date"),
        "perception_id": json_cliente.get("perception_id"),
        "phonekey": json_cliente.get("phonekey"),
        "debt": json_cliente.get("debt"),
        "duedebt": json_cliente.get("duedebt"),
        "speed_limited": json_cliente.get("speed_limited"),
        "status": json_cliente.get("status"),
        "enable_date": json_cliente.get("enable_date"),
        "block_date": json_cliente.get("block_date"),
        "created_at": json_cliente.get("created_at"),
        "updated_at": json_cliente.get("updated_at"),
        "deleted_at": json_cliente.get("deleted_at"),
        "temporary": json_cliente.get("temporary"),
    }

def nightly_sync():
    init_db()
    db = Database()
    print("\n[SYNC] 🚀 Iniciando Sincronización...\n")
    try:
        sync_nodes(db)
        sync_secrets(db)
        sync_onus(db)
        sync_plans(db)
        sync_connections(db) # Vuelve a usar el método "todo de una vez"
        sync_clientes(db)
        
        print("\n   ↳ Cruzando datos (Match Connections)...", end=" ", flush=True)
        db.match_connections()
        db.commit()
        print("✅ OK")
        
        config.logger.info("[SYNC] Sincronización completa finalizada.")
    finally:
        db.close()
        print("\n[SYNC] ✨ Finalizado.\n")

if __name__ == "__main__":
    nightly_sync()
```

---

## F. app/main.py (wiring y seguridad)

```python
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from app import config
from app.services.diagnostico import consultar_diagnostico
from app.security import get_api_key
from app.db.sqlite import Database # Importación necesaria
from app.config import logger
from app.clients import mikrotik
from app.oraculo_router import router as oraculo_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Beholder - Diagnóstico Centralizado")

app.include_router(oraculo_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    config.logger.info("Servicio Beholder iniciado.")

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    key = request.headers.get("x-api-key")
    if key != config.API_KEY:
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)

@app.get("/health")
def health():
    return {"ok": True, "service": "beholder", "status": "running"}

@app.get("/diagnosis/{pppoe_user}")
def diagnosis(pppoe_user: str):
    try:
        row = consultar_diagnostico(pppoe_user)
    except Exception as e:
        logger.exception(f"Error en diagnóstico de {pppoe_user}")
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in row:
        raise HTTPException(status_code=404, detail=row["error"])
    return row

# --- NUEVO ENDPOINT DE BÚSQUEDA ---
@app.get("/search")
def search_clients(q: str):
    """
    Busca clientes por nombre, dirección o PPPoE (Gestión + OLT).
    """
    if not q or len(q) < 3:
        return []
    
    db = Database()
    try:
        results = db.search_client(q)
        return results
    except Exception as e:
        logger.exception(f"Error buscando cliente: {q}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/")
def read_root(api_key: str = Depends(get_api_key)):
    return {"status": "ok", "service": "Beholder API"}

@app.get("/live/{pppoe_user}")
def live_traffic(pppoe_user: str):
    """
    Obtiene el consumo en tiempo real resolviendo internamente 
    en qué nodo está el cliente.
    """
    db = Database()
    try:
        # 1. Buscamos la IP del router en nuestra DB local
        router_data = db.get_router_for_pppoe(pppoe_user)
        
        if not router_data:
            # Si no está en la tabla connections, no sabemos a qué router preguntarle
            return {
                "status": "error", 
                "detail": "Cliente no vinculado o no encontrado en base de datos local."
            }
            
        router_ip, router_port = router_data
        
        # Usamos puerto default si la DB lo tiene null/vacío
        if not router_port:
            router_port = config.MK_PORT
        
        # 2. Consultamos al Mikrotik
        trafico = mikrotik.obtener_trafico_en_vivo(router_ip, pppoe_user, int(router_port))
        
        if "error" in trafico:
             return {"status": "error", "detail": trafico["error"]}
             
        # 3. Formateamos respuesta
        rx_mbps = round(int(trafico["rx"]) / 1000000, 2)
        tx_mbps = round(int(trafico["tx"]) / 1000000, 2)
        
        return {
            "status": "ok",
            "router_ip": router_ip, # Dato útil para debug, opcional
            "download_mbps": rx_mbps,
            "upload_mbps": tx_mbps,
            "raw": trafico
        }
        
    except Exception as e:
        config.logger.error(f"Fallo endpoint live traffic: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
```

---

## G. requirements.txt (estado correcto)

```txt
# Requisitos del proyecto Beholder

# Framework web
fastapi==0.115.0
uvicorn[standard]==0.30.0

# Base de datos

# Cliente Mikrotik
RouterOS-api==0.21.0

# Logging y utilidades
python-dotenv==1.0.1    # para manejar variables de entorno (.env)
loguru==0.7.2
# Dependencias comunes
requests==2.32.3        # para llamadas HTTP (SmartOLT, ISPCube)
influxdb-client==1.46.0 # cliente de InfluxDB v2
```

---

## H. Prompt maestro para otra sesion de Copilot

```text
Contexto:
Estamos migrando Beholder 2026 a este repositorio (entorno con PostgreSQL). Necesitamos replicar exactamente la logica funcional, performance y resiliencia de Oraculo 2.0.

Instrucciones:
1) Implementar los modulos segun docs/migracion_beholder_2026_codigo_anexos.md.
2) NO cambiar contratos HTTP ni payloads de salida.
3) Adaptar SOLO la capa de persistencia desde SQLite a PostgreSQL, manteniendo mismas firmas y campos esperados por servicios.
4) Mantener comportamiento de errores controlados para SmartOLT (sin .json() sobre dict de error).
5) Mantener cache TTL de sesiones Graylog y concurrencia limitada en consultas Influx por segmento.
6) Mantener observabilidad en endpoint /api/v1/oraculo/trafico-pppoe/{usuario_pppoe}.
7) Agregar/validar dependencia influxdb-client en requirements del nuevo entorno.
8) Entregar pruebas de smoke:
   - /health
   - /api/v1/oraculo/trafico-pppoe/{usuario}?rango=24h
   - /diagnosis/{usuario}
   - flujo con SmartOLT caido/degradado sin excepcion no controlada

Criterio de aceptacion:
- Endpoints responden con mismo contrato.
- No hay regresiones en diagnostico.
- No hay tracebacks por parsing de SmartOLT.
- Logs incluyen metrica estructurada de oraculo_pppoe_metrics.
```

---

## I. Checklist rapido de validacion en el entorno destino

1. Dependencias:
- instalar requirements y confirmar `influxdb_client` importable.

2. Arranque:
- servicio levanta y `/health` responde 200.

3. Seguridad:
- middleware `x-api-key` activo.

4. Oraculo:
- `trafico-pppoe` devuelve lista de puntos o lista vacia, nunca 500 por parseo SmartOLT.

5. Diagnostico:
- `diagnosis` retorna `onu_status_smrt` dict, `onu_signal_smrt` dict, `onu_vlan` list.

6. Observabilidad:
- aparece linea `oraculo_pppoe_metrics` con tiempos y segmentos.
