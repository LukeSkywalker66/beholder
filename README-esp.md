👁️ Beholder
Herramienta Centralizada de Diagnóstico y Triage para ISP

📖 Descripción General
Beholder es el backend de diagnóstico unificado diseñado para 2F Internet. Su función principal es agregar datos técnicos de múltiples sistemas de gestión del ISP (SmartOLT, ISPCube, Mikrotik) para generar un reporte de estado instantáneo de suscriptores de fibra óptica e inalámbricos.

Expone una interfaz FastAPI que es consumida por el frontend o chatbots para determinar rápidamente si una interrupción del servicio requiere el despacho físico de un técnico o si puede resolverse de forma remota.

✨ Características Principales
API Unificada: Un único endpoint /diagnosis/{pppoe_user} devuelve una visión de 360° del cliente.

Integración Multi-Vendor: Conecta simultáneamente con SmartOLT (Fibra), ISPCube (CRM/Facturación) y Mikrotik (Red).

Alto Rendimiento: Utiliza SQLite como caché local para búsquedas instantáneas, evitando la lentitud de las APIs externas durante la atención al cliente.

Sincronización Nocturna: Tareas automatizadas (app.jobs.sync) mantienen la base local actualizada con los últimos datos de suscriptores.

Seguridad: Protegido mediante autenticación por API Key y limitación de tasa (rate limiting).

📂 Estructura del Proyecto
Plaintext

beholder/
├── app/
│   ├── __init__.py
│   ├── main.py          # Punto de entrada de FastAPI
│   ├── config.py        # Carga de variables de entorno y Logger
│   ├── security.py      # Middleware de API Key
│   ├── clients/         # Adaptadores de APIs externas
│   │   ├── ispcube.py
│   │   ├── mikrotik.py
│   │   └── smartolt.py
│   ├── db/              # Capa de acceso a datos
│   │   └── sqlite.py    # Operaciones CRUD en SQLite
│   ├── jobs/            # Tareas en segundo plano
│   │   ├── sync.py      # Lógica principal de sincronización
│   │   └── debug_ispcube.py
│   ├── services/        # Lógica de negocio
│   │   └── diagnostico.py
│   └── utils/
│       └── safe_call.py
├── config/
│   └── .env             # Variables de entorno (Ignorado por Git)
├── data/
│   ├── diag.db          # Archivo de base de datos local
│   └── logs/            # Logs de la aplicación
├── docs/                # Documentación del proyecto y ADRs
├── requirements.txt     # Dependencias de Python
└── README.md
🚀 Guía de Inicio Rápido
1. Requisitos Previos
Python 3.10 o superior.

Entorno virtual (recomendado).

2. Instalación
Bash

# Clonar el repositorio
git clone <url-de-tu-repo>
cd beholder

# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows:
.\venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
3. Configuración
Creá un archivo .env en la carpeta config/. Podés usar el siguiente ejemplo basado en app/config.py:

Ini, TOML

# config/.env

# General
API_KEY=tu_clave_secreta_aqui
DB_PATH=data/diag.db

# SmartOLT
SMARTOLT_BASEURL=https://tu-instancia-smartolt.com/api
SMARTOLT_TOKEN=tu_token_smartolt

# Mikrotik (Gateway por Defecto)
MK_HOST=192.168.1.1
MK_USER=admin
MK_PASS=password_admin
MK_PORT=8728

# ISPCube
ISPCUBE_BASEURL=https://api.ispcube.com
ISPCUBE_APIKEY=tu_apikey_ispcube
ISPCUBE_USER=tu_usuario
ISPCUBE_PASSWORD=tu_password
ISPCUBE_CLIENTID=tu_client_id

# Oráculo - InfluxDB
ORACULO_INFLUX_URL=http://tu-influx:8086
ORACULO_INFLUX_TOKEN=tu_token_influx
ORACULO_INFLUX_ORG=tu_org
ORACULO_INFLUX_TIMEOUT_MS=10000

# Oráculo - Buckets / measurements (downsampling)
ORACULO_INFLUX_RAW_BUCKET=netflow
ORACULO_INFLUX_RESUMEN_BUCKET=netflow_resumen
ORACULO_INFLUX_RAW_MEASUREMENT=netflow
ORACULO_INFLUX_RESUMEN_MEASUREMENT=resumen_5m
ORACULO_INFLUX_IN_BYTES_FIELD=in_bytes

# Oráculo - Graylog
ORACULO_GRAYLOG_URL=http://tu-graylog:9000
ORACULO_GRAYLOG_USER=usuario_o_token
ORACULO_GRAYLOG_PASSWORD=password_o_token
ORACULO_GRAYLOG_TIMEOUT_SEC=15
4. Ejecución de la Aplicación
Opción A: Correr el Servidor API (Desarrollo) Esto inicia el backend en el puerto 8500 (puerto por defecto en producción).

Bash

uvicorn app.main:app --reload --port 8500
Podés verificar el estado en: http://localhost:8500/health

Opción B: Correr la Sincronización Para disparar manualmente el proceso nocturno (descarga de clientes, ONUs, etc.):

Bash

# Ejecutar como módulo desde la raíz del proyecto
python -m app.jobs.sync
📡 Ejemplos de Uso de la API
Obtener Diagnóstico de Cliente

Bash

curl -X GET "http://127.0.0.1:8500/diagnosis/juan_perez_pppoe" \
     -H "x-api-key: tu_clave_secreta_aqui"
Buscar Cliente (Nuevo)

Bash

curl -X GET "http://127.0.0.1:8500/search?q=Juan%20Perez" \
     -H "x-api-key: tu_clave_secreta_aqui"

Tráfico por IP (Oráculo)

Bash

curl -X GET "http://127.0.0.1:8500/api/v1/oraculo/trafico/172.17.1.160?rango=15m" \
     -H "x-api-key: tu_clave_secreta_aqui"

Rangos soportados para tráfico:
- Tiempo real: 15m, 30m, 60m (bucket crudo)
- Histórico: 12h, 24h, 7d, 30d (bucket resumido)

Respuesta de tráfico:
- Lista de puntos con: tiempo, descarga_mbps, subida_mbps

Tráfico por PPPoE (Oráculo)

Bash

curl -X GET "http://127.0.0.1:8500/api/v1/oraculo/trafico-pppoe/usuario_pppoe?rango=24h" \
     -H "x-api-key: tu_clave_secreta_aqui"

Este endpoint orquesta Graylog + InfluxDB para devolver una serie continua de consumo por usuario PPPoE, aunque cambie de IP durante el período.
Además, cruza la IP del nodo del cliente con el mapeo interno de Influx para reducir la búsqueda y evitar conflictos entre nodos.

Historial de sesiones PPPoE (Oráculo)

Bash

curl -X GET "http://127.0.0.1:8500/api/v1/oraculo/sesiones/usuario_pppoe?limite=20" \
     -H "x-api-key: tu_clave_secreta_aqui"

Diagnóstico de integraciones (Oráculo)

Bash

curl -X GET "http://127.0.0.1:8500/api/v1/oraculo/debug" \
     -H "x-api-key: tu_clave_secreta_aqui"
🛠 Despliegue (Producción)
El proyecto está configurado para correr vía systemd en Debian.

Servicio: /etc/systemd/system/beholder.service

Logs: journalctl -u beholder.service -f

Actualización: Hacer push a la rama de producción dispara el hook automático:

Bash

git push production main