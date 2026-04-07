import os
import logging
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join("config", ".env"))

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
ORACULO_INFLUX_RESUMEN_SENTIDO_TAG = os.getenv("ORACULO_INFLUX_RESUMEN_SENTIDO_TAG", "sentido")
ORACULO_INFLUX_SENTIDO_DESCARGA = os.getenv("ORACULO_INFLUX_SENTIDO_DESCARGA", "descarga")
ORACULO_INFLUX_SENTIDO_SUBIDA = os.getenv("ORACULO_INFLUX_SENTIDO_SUBIDA", "subida")
ORACULO_INFLUX_REALTIME_WINDOW_SECONDS = int(os.getenv("ORACULO_INFLUX_REALTIME_WINDOW_SECONDS", "60"))
ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS = int(os.getenv("ORACULO_INFLUX_RESUMEN_WINDOW_SECONDS", "300"))
ORACULO_INFLUX_TIMEOUT_MS = int(os.getenv("ORACULO_INFLUX_TIMEOUT_MS", "10000"))
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