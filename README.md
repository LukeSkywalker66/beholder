# Beholder

Beholder es un servicio de diagnóstico centralizado para ISP.  
Su objetivo es unificar consultas técnicas a SmartOLT, Mikrotik y GenieACS, resolviendo diagnósticos de clientes a partir de su usuario PPPoE.

## ✨ Características
- API HTTP basada en FastAPI.
- Endpoint `/diagnostico?pppoeUser=...` que devuelve panorama técnico.
- Sincronización diaria de suscriptores desde SmartOLT.
- Base local (SQLite/Redis) para lookups rápidos.
- Seguridad con API key y rate limiting.
- Logs estructurados con Loguru.

## 📂 Estructura del proyecto

beholder/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app principal
│   ├── config.py        # carga de variables .env
│   ├── security.py      # API key + rate limiting
│   ├── models.py        # esquemas Pydantic
│   ├── services/        # lógica de diagnóstico
│   │   └── diagnostico.py
│   ├── clients/         # conectores a APIs externas
│   │   ├── smartolt.py
│   │   ├── mikrotik.py
│   │   └── genieacs.py
│   ├── db/              # acceso a base local
│   │   └── sqlite.py
│   └── jobs/            # tareas programadas
│       └── sync_smartolt.py
├── config/
│   └── .env.example     # variables de entorno
├── tests/
│   └── test_api.py      # pruebas unitarias
├── requirements.txt
├── README.md
└── .gitignore

## 🚀 Uso rápido

Levantar el servicio en modo desarrollo:

```bash
uvicorn app.main:app --reload --port 8088

curl -H "x-api-key: your-key" "http://127.0.0.1:8088/diagnostico?pppoeUser=usuarioprueba"


http://127.0.0.1:8088/health