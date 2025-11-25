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