from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

def sync_secrets(db):
    nodes = db.get_nodes_for_sync()
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos para sync secrets.")
        print("   ↳ ⚠️ No hay nodos para consultar Mikrotik.")
        return

    # Borramos para regenerar, ahora la tabla soporta duplicados por nodo
    db.cursor.execute("DELETE FROM ppp_secrets")
    
    print(f"   ↳ Consultando {len(nodes)} Mikrotiks:")
    total_secrets = 0
    count_ok = 0

    for node in nodes:
        ip = node["ip"]
        name = node["name"]
        port = node["port"] if node["port"] else config.MK_PORT
        
        # Log visual en consola
        print(f"      > {name} ({ip})...", end=" ", flush=True)
        
        try:
            secrets = mikrotik.get_all_secrets(ip, port)
            if secrets is not None:
                for s in secrets:
                    db.insert_secret(s, ip)
                count = len(secrets)
                total_secrets += count
                count_ok += 1
                print(f"✅ ({count})")
            else:
                print("⚠️ Sin respuesta")
        except Exception as e:
            print(f"❌ Error: {e}")
            config.logger.error(f"[SYNC] Error en router {ip}: {e}")
    
    db.commit()
    config.logger.info(f"[SYNC] {total_secrets} secrets sincronizados de {count_ok}/{len(nodes)} nodos.")
    print(f"   ↳ Resumen: {total_secrets} secrets guardados.")

# ... (El resto de las funciones sync_onus, sync_nodes, etc. se mantienen igual, solo asegurate que llamen a este sync_secrets) ...

# Función main completa para copiar:
def nightly_sync():
    init_db()
    db = Database()
    print("\n[SYNC] 🚀 Iniciando Sincronización...\n")
    try:
        # 1. Nodos (ISPCube)
        print("   ↳ Buscando Nodos en ISPCube...", end=" ", flush=True)
        try:
            nodes = ispcube.obtener_nodos()
            if nodes:
                db.cursor.execute("DELETE FROM nodes")
                for n in nodes: db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
                print(f"✅ ({len(nodes)})")
            else: print("⚠️ Vacío")
        except Exception as e: print(f"❌ {e}")

        # 2. Secrets (Mikrotik) - AHORA DETALLADO
        sync_secrets(db)

        # 3. ONUs
        print("   ↳ Consultando SmartOLT...", end=" ", flush=True)
        try:
            onus = smartolt.get_all_onus()
            if onus:
                db.cursor.execute("DELETE FROM subscribers")
                for o in onus: 
                    db.insert_subscriber(o.get("unique_external_id"), o.get("sn"), o.get("olt_name"), o.get("olt_id"), o.get("board"), o.get("port"), o.get("onu"), o.get("onu_type_id"), o.get("name"), o.get("mode"))
                print(f"✅ ({len(onus)})")
            else: print("⚠️ Vacío")
        except Exception as e: print(f"❌ {e}")

        # 4. Datos Admin
        # ... (Tu código existente para planes, conexiones, clientes) ...
        # Solo asegúrate de llamar a db.match_connections() al final.
        
        # Para abreviar, asumo que tienes el resto. Lo importante fue sync_secrets.
        
        print("   ↳ Cruzando datos (Match)...", end=" ", flush=True)
        db.match_connections()
        db.commit()
        print("✅ OK")
        
    finally:
        db.close()
        print("\n[SYNC] ✨ Finalizado.\n")

if __name__ == "__main__":
    nightly_sync()