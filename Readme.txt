👁️ Beholder
Centralized ISP Diagnostic & Triage Tool

📖 Overview
Beholder is a unified diagnostic backend designed for 2F Internet. It aggregates technical data from multiple ISP management systems (SmartOLT, ISPCube, Mikrotik) to provide a single, instantaneous status report for fiber and wireless subscribers.

It exposes a FastAPI interface consumed by the frontend or chatbots to determine if a service interruption requires a physical technician dispatch or can be resolved remotely.

✨ Key Features

Unified API: Single endpoint /diagnosis/{pppoe_user} returns a 360° view of the client.



Multi-Vendor Integration: Connects simultaneously to SmartOLT (Fiber), ISPCube (CRM/Billing), and Mikrotik (Network).


High Performance: Uses SQLite as a local cache for instant lookups, avoiding slow external API calls during customer interaction.


Nightly Synchronization: Automated jobs (app.jobs.sync) keep the local cache updated with the latest subscriber data.


Security: Protected via API Key authentication and rate limiting.

📂 Project Structure
Plaintext

beholder/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI Entry Point
│   ├── config.py        # Env var loader & Logger config
│   ├── security.py      # API Key Middleware
│   ├── clients/         # External API Adapters
│   │   ├── ispcube.py
│   │   ├── mikrotik.py
│   │   └── smartolt.py
│   ├── db/              # Database Access Layer
│   │   └── sqlite.py    # SQLite CRUD operations
│   ├── jobs/            # Background Tasks
│   │   ├── sync.py      # Main synchronization logic
│   │   └── debug_ispcube.py
│   ├── services/        # Business Logic
│   │   └── diagnostico.py
│   └── utils/
│       └── safe_call.py
├── config/
│   └── .env             # Environment variables (GitIgnored)
├── data/
│   ├── diag.db          # Local Database File
│   └── logs/            # App logs
├── docs/                # Project Documentation & ADRs
├── requirements.txt     # Python Dependencies
└── README.md
🚀 Getting Started
1. Prerequisites
Python 3.10+

Virtual Environment (recommended)

2. Installation
Bash

# Clone the repository
git clone <your-repo-url>
cd beholder

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
.\venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
3. Configuration
Create a .env file in the config/ directory. You can copy the example or use the following template based on app/config.py:

Ini, TOML

# config/.env

# General
API_KEY=your_secret_api_key_here
DB_PATH=data/diag.db

# SmartOLT
SMARTOLT_BASEURL=https://your-smartolt-instance.com/api
SMARTOLT_TOKEN=your_smartolt_token

# Mikrotik (Gateway Default)
MK_HOST=192.168.1.1
MK_USER=admin
MK_PASS=admin_password
MK_PORT=8728

# ISPCube
ISPCUBE_BASEURL=https://api.ispcube.com
ISPCUBE_APIKEY=your_ispcube_apikey
ISPCUBE_USER=your_user
ISPCUBE_PASSWORD=your_password
ISPCUBE_CLIENTID=your_client_id
4. Running the Application
Option A: Run the API Server (Development) This starts the backend at port 8500 (default for production).

Bash

uvicorn app.main:app --reload --port 8500
Access the health check at: http://localhost:8500/health

Option B: Run the Synchronization Job To manually trigger the nightly sync process (download customers, ONUs, etc.):

Bash

# Run as a module from the root directory
python -m app.jobs.sync
📡 API Usage Example
Get Client Diagnosis

Bash

curl -X GET "http://127.0.0.1:8500/diagnosis/john_doe_pppoe" \
     -H "x-api-key: your_secret_api_key_here"
Search Client (New)

Bash

curl -X GET "http://127.0.0.1:8500/search?q=Juan%20Perez" \
     -H "x-api-key: your_secret_api_key_here"
🛠 Deployment (Production)
The project is configured to run via systemd on Debian.

Service Path: /etc/systemd/system/beholder.service

Logs: journalctl -u beholder.service -f

Update: Push to the production branch triggers the git hook:

Bash

git push production main