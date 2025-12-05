

# 📖 Guía de Proyecto Beholder

## 1. Introducción
- **Propósito del sistema**: diagnóstico centralizado de clientes ISP (fibra y antena).
- **Contexto**: múltiples sistemas dispersos (SmartOLT, ISPCube, cnMaestro, Hest).
- **Objetivo**: unificar información para operadores y técnicos, simplificar soporte y escalar servicio.

---

## 2. Entorno de Producción
### 2.1 Servidor Debian
- Ruta principal: `/home/administrador/apps/beholder`
- Repositorio Git: `/home/administrador/repos/beholder.git`
- Servicio systemd: `/etc/systemd/system/beholder.service`
- Configuración Nginx: `/etc/nginx/sites-enabled/beholder.conf`
- Logs: `/var/log/beholder/`

### 2.2 Deploy
- Comando: `git push production main`
- Hook: `post-receive` → actualiza código y reinicia servicio.
- Sudoers: reglas NOPASSWD para `systemctl reload nginx` y `systemctl restart beholder.service`.

---

## 3. Estructura del Repositorio
```
beholder/
├── backend/          # API y lógica de negocio
│   ├── sync.py       # Sincronización nocturna
│   ├── db.py         # Acceso a base de datos
│   └── clients/      # Integraciones externas (smartolt.py, ispcube.py, cnmaestro.py)
├── frontend/         # React UI
├── hooks/            # Scripts de deploy
├── docs/             # Documentación en Markdown
└── tests/            # Pruebas unitarias
```

---

## 4. Repositorio GitHub
- URL: `https://github.com/<org>/beholder`
- Estado: público/privado (definir).
- Políticas de acceso: quién puede hacer push, revisión de PRs.
- Consideraciones de seguridad: no incluir credenciales en el repo.

---

## 5. Flujo de Trabajo
- **Commit y Push**: desarrollador hace cambios → `git push production main`.
- **Hook de Deploy**: recibe push → actualiza código → reinicia servicio.
- **Sync nocturno**: `cron` ejecuta `sync.py` → actualiza DB con datos externos.
- **Operación diaria**: operadores usan frontend para diagnóstico.

---

## 6. Documentación Técnica
- Definición de cada archivo fuente.
- Ejemplos de queries SQL comunes.
- Integraciones externas (SmartOLT, ISPCube, cnMaestro).
- ADRs relevantes.

---

## 7. Roadmap
- Migración futura a PostgreSQL.
- Extensión de diagnóstico con alarmas cnMaestro.
- Integración con stock y helpdesk.

