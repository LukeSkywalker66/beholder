import time
from app.db.sqlite import Database, init_db
from app.clients import ispcube
from app.jobs.sync import mapear_cliente, insertar_contactos_relacionados

def debug_sync_clientes():
    print("🔵 [DEBUG] Iniciando entorno local...")
    
    # 1. Inicializar DB local (creará diag.db en tu carpeta local)
    init_db()
    db = Database()

    print("⏳ [DEBUG] Consultando API Clientes de ISPCube...")
    start_time = time.time()
    
    try:
        # Llamada directa a la función que falla
        clientes = ispcube.obtener_clientes()
        
        duration = time.time() - start_time
        
        if clientes:
            print(f"✅ [ÉXITO] Se descargaron {len(clientes)} clientes en {duration:.2f} segundos.")
            
            # Guardamos para verificar que la DB local quede bien
            print("💾 [DEBUG] Guardando en SQLite local...")
            db.cursor.execute("DELETE FROM clientes")
            db.cursor.execute("DELETE FROM clientes_emails")
            db.cursor.execute("DELETE FROM clientes_telefonos")

            for c in clientes:
                db.insert_cliente(mapear_cliente(c))
                insertar_contactos_relacionados(db, c)
            
            db.commit()
            print("✅ [FIN] Datos guardados correctamente.")
        else:
            print(f"⚠️ [WARN] La API respondió OK pero la lista está vacía. Tiempo: {duration:.2f}s")

    except Exception as e:
        duration = time.time() - start_time
        print(f"\n❌ [ERROR CRÍTICO] La API falló a los {duration:.2f} segundos.")
        print(f"   Tipo de error: {type(e).__name__}")
        print(f"   Detalle: {e}")

    finally:
        db.close()

if __name__ == "__main__":
    debug_sync_clientes()