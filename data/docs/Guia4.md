
# 📖 Documentación Frontend Beholder

## 1. Introducción
El frontend de Beholder es una aplicación **React + Vite** que consume la API backend (FastAPI).  
Su propósito es ofrecer a los operadores una interfaz clara y amigable para realizar diagnósticos de clientes ISP.

---

## 2. Entorno de Producción
- **Servidor Debian**: mismo host que el backend.  
- **Web server**: Nginx sirve los archivos estáticos del build (`dist/`).  
- **Ruta típica de deploy**:  
  - Código fuente: `/home/administrador/apps/beholder-frontend`  
  - Build: `/home/administrador/apps/beholder-frontend/dist`  
  - Configuración Nginx: `/etc/nginx/sites-enabled/beholder-frontend.conf`  
- **Variables de entorno**: `.env` para backend y `.env2` para frontend.  
  - `VITE_API_URL=http://138.59.172.24:8500`  
  - `VITE_API_KEY=Zo9fUbuGS5Qh...`  

---

## 3. Estructura del Frontend
```
src/
├── App.tsx             # Layout principal, sidebar + resultados
├── App.css             # Estilos globales, grilla, dark mode, responsive
├── assets/
│   └── beholder2.png   # Logo
├── components/
│   ├── SearchBox.tsx   # Input PPPoE + botón buscar
│   ├── OutputBox.tsx   # Renderizado de diagnóstico normalizado
│   └── CopyButton.tsx  # Botón para copiar diagnóstico al portapapeles
└── env2                # Variables de entorno (API URL y API Key)
```

---

## 4. Definición de Archivos Fuente

### `App.tsx`
- Layout dividido en dos paneles:
  - **Sidebar**: logo, título, `SearchBox`.  
  - **Results**: muestra `OutputBox` con datos del diagnóstico.  
- Estado global `resultData` que se actualiza con la búsqueda.

### `SearchBox.tsx`
- Input para PPPoE.  
- Botón “Buscar” que llama al backend (`/diagnosis/{pppoe_user}`).  
- Maneja estados de `loading` y `error`.  
- Envía resultado al padre (`App.tsx`) vía `onResult`.

### `OutputBox.tsx`
- Recibe `data` y lo muestra en grilla.  
- Traduce estados técnicos a lenguaje operator-friendly (ej. `Online → En línea`).  
- Incluye botón `CopyButton` para copiar diagnóstico en texto plano.  
- Usa estilos condicionales (`estado-ok`, `estado-error`) para resaltar estado PPPoE y ONU.

### `CopyButton.tsx`
- Copia al portapapeles el texto normalizado del diagnóstico.  
- Feedback visual: ✔ Copiado durante 2 segundos.  
- Implementa fallback para navegadores sin `navigator.clipboard`.

### `App.css`
- Define layout (sidebar + results).  
- Grilla responsive para resultados.  
- Estilos condicionales (`estado-ok`, `estado-error`).  
- Dark mode automático con `prefers-color-scheme`.  
- Responsive para móviles (columna única).

---

## 5. Flujo de Diagnóstico en Frontend
1. Operador ingresa PPPoE en `SearchBox`.  
2. Se llama al backend con `fetch` y API Key.  
3. Respuesta JSON se guarda en `resultData`.  
4. `OutputBox` muestra diagnóstico normalizado.  
5. Operador puede copiar texto con `CopyButton`.  

---

## 6. Deploy Frontend
- Build con Vite:
  ```bash
  npm run build
  ```
- Copiar carpeta `dist/` al servidor Debian.  
- Configurar Nginx para servir `dist/` como sitio estático.  
- Asegurar que `VITE_API_URL` apunte al backend en producción.  

---

## 7. Roadmap Frontend
- Extender `OutputBox` con más campos de cliente (teléfonos, emails).  
- Internacionalización (i18n) para soportar múltiples idiomas.  
- Mejorar feedback visual en errores de conexión.  
- Dashboard con métricas de sincronización (`sync_status`).  

