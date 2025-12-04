## 2. Entorno de Producción

### 2.1 Servidor
- **Sistema operativo**: Debian GNU/Linux 12.12 (Bookworm)
- **Hostname**: debian-acsserver
- **Usuario de despliegue**: administrador
- **IP pública**: 138.59.172.24
- **Ruta del código**: /home/administrador/apps/beholder
- **Repositorio bare Git**: /home/administrador/repos/beholder.git

### 2.2 Servicio Beholder
- **Archivo systemd**: /etc/systemd/system/beholder.service
- **Comandos útiles**:
  - `systemctl status beholder.service`
  - `systemctl restart beholder.service`
- **Logs**:
  - API: /home/administrador/apps/beholder/data/logs/sync.log
  - Systemd: `journalctl -u beholder.service`

### 2.3 API Backend
- **Puerto expuesto**: 8500
- **URL interna**: http://localhost:8500
- **URL externa**: http://138.59.172.24:8500
- **Endpoints principales**:
  - `/diagnosis/{pppoe_user}`
  - `/health`

### 2.4 Nginx
- **Archivo de configuración**: /etc/nginx/sites-enabled/beholder.conf
- **Función**: proxy inverso hacia FastAPI en puerto 8500
- **Certificados SSL**: /etc/letsencrypt/live/ (si se usa HTTPS)