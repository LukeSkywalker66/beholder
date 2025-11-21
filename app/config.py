import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join("config", ".env"))

API_KEY = os.getenv("API_KEY")
SMARTOLT_BASEURL = os.getenv("SMARTOLT_BASEURL")
SMARTOLT_TOKEN = os.getenv("SMARTOLT_TOKEN")
MK_HOST = os.getenv("MK_HOST")
MK_USER = os.getenv("MK_USER")
MK_PASS = os.getenv("MK_PASS")
GENIEACS_URL = os.getenv("GENIEACS_URL")
DB_PATH = os.getenv("DB_PATH")