

# 📖 Documentación del Proyecto Beholder

## 1. Resumen Ejecutivo
- **Propósito del sistema**: diagnóstico centralizado de clientes ISP (fibra y antena).
- **Contexto**: múltiples sistemas dispersos (SmartOLT, ISPCube, cnMaestro, Hest).
- **Objetivo**: unificar información para operadores y técnicos, simplificar soporte y escalar servicio.

---

## 2. Requerimientos del Proyecto
### 2.1 Funcionales
- Diagnóstico de clientes por PPPoE/ONU/antena.
- Sincronización nocturna de datos (clientes, conexiones, planes, nodos, suscriptores).
- Integración con APIs externas (SmartOLT, ISPCube, cnMaestro).
- Interfaz web operator-friendly.
- Logging y auditoría de sincronización.

### 2.2 No Funcionales
- Seguridad: control de acceso, sudoers configurado para deploy.
- Performance: consultas rápidas con índices.
- Mantenibilidad: modularidad en mappers, helpers y DB.
- Escalabilidad: soporte para fibra y antena.

---

## 3. Arquitectura del Sistema (C4 Model)
### 3.1 Contexto
- Beholder como sistema central dentro del ISP.
- Relación con SmartOLT, ISPCube, cnMaestro, Hest.

### 3.2 Contenedores
- Backend Python (FastAPI/Flask).
- Frontend React.
- Base de datos SQLite.
- Servicios externos (APIs).

### 3.3 Componentes
- `sync.py`: sincronización nocturna.
- `clients/`: módulos de integración (smartolt.py, ispcube.py, cnmaestro.py).
- `db.py`: acceso a base de datos.
- `frontend/`: UI operator-friendly.

### 3.4 Código
- Funciones clave (`get_diagnosis`, `sync_subscribers_aire`, etc.).
- Helpers y mappers.

---

## 4. Base de Datos
- **Tablas principales**:
  - `clientes`
  - `connections`
  - `subscribers` (fibra)
  - `subscribers_aire` (antenas)
  - `nodes`
  - `plans`
- **Relaciones**:
  - `clientes` ↔ `connections`
  - `connections` ↔ `subscribers` / `subscribers_aire`
  - `connections` ↔ `nodes`, `plans`

---

## 5. Integraciones Externas
- **SmartOLT API**: ONUs, OLTs.
- **ISPCube API**: clientes, planes, conexiones.
- **cnMaestro API**: antenas, alarmas, suscriptores.
- **Hest Helpdesk**: tickets internos.

---

## 6. ADR (Architecture Decision Records)
- **ADR-001**: Usar SQLite en primera versión por simplicidad.
- **ADR-002**: Deploy vía git hooks + sudoers NOPASSWD.
- **ADR-003**: Separar mappers, helpers y DB para modularidad.
- **ADR-004**: Integrar cnMaestro para clientes de antena.

---

## 7. Guía de Operación
- **Deploy**: `git push production main` → hook → reload nginx + restart beholder.
- **Sync manual**: `python sync.py`.
- **Logs**: ubicaciones y formato.
- **Troubleshooting**: errores comunes (sudoers, permisos, API tokens).

---

## 8. Roadmap
- Migrar DB a PostgreSQL para mayor escala.
- Extender diagnóstico con alarmas cnMaestro.
- Integración con stock y helpdesk.

---
