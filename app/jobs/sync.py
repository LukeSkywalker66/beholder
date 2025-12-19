from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

# --- FUNCIONES DE SINCRONIZACIÓN ---

def sync_nodes(db):
    print("   ↳ Buscando Nodos en ISPCube...", end=" ", flush=True)
    try:
        nodes = ispcube.obtener_nodos()
        if nodes:
            db.cursor.execute("DELETE FROM nodes")
            for n in nodes:
                db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
            config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")
            db.log_sync_status("ispcube", "ok", f"{len(nodes)} nodos sincronizados")
            print(f"✅ ({len(nodes)} encontrados)")
        else:
            print("⚠️ Lista vacía")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error Nodos: {e}")

def sync_secrets(db):
    # Lógica detallada para Mikrotik (LA QUE TE GUSTA)
    nodes = db.get_nodes_for_sync()
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos para sync secrets.")
        print("   ↳ ⚠️ No hay nodos para consultar Mikrotik.")
        return

    db.cursor.execute("DELETE FROM ppp_secrets")
    
    print(f"   ↳ Consultando {len(nodes)} Mikrotiks:")
    total_secrets = 0
    count_ok = 0

    for node in nodes:
        ip = node["ip"]
        name = node["name"]
        port = node["port"] if node["port"] else config.MK_PORT
        
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

def sync_onus(db):
    print("   ↳ Consultando SmartOLT...", end=" ", flush=True)
    try:
        onus = smartolt.get_all_onus()
        if onus:
            db.cursor.execute("DELETE FROM subscribers")
            for onu in onus:
                db.insert_subscriber(
                    onu.get("unique_external_id"), 
                    onu.get("sn"), 
                    onu.get("olt_name"), 
                    onu.get("olt_id"), 
                    onu.get("board"), 
                    onu.get("port"), 
                    onu.get("onu"), 
                    onu.get("onu_type_id"), 
                    onu.get("name"), 
                    onu.get("mode")
                )
            db.log_sync_status("smartolt", "ok", f"{len(onus)} ONUs sincronizadas")
            config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
            print(f"✅ ({len(onus)} ONUs)")
        else:
            db.log_sync_status("smartolt", "empty", "SmartOLT no devolvió datos")
            print("⚠️ Sin datos")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error SmartOLT: {e}")

def sync_plans(db):
    print("   ↳ [ISPCube] Bajando Planes...", end=" ", flush=True)
    try:
        planes = ispcube.obtener_planes()
        if planes:
            db.cursor.execute("DELETE FROM plans")
            for p in planes:
                db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
            config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")
            db.log_sync_status("ispcube", "ok", f"{len(planes)} planes sincronizados")
            print(f"✅ ({len(planes)})")
        else: print("⚠️")
    except Exception as e: print(f"❌ {e}")

def sync_connections(db):
    # AQUI ESTA EL ARREGLO CLAVE: PAGINACIÓN
    print("\n   ↳ [ISPCube] Bajando Conexiones (Por Lotes)...")
    try:
        db.cursor.execute("DELETE FROM connections")
        db.commit()
        
        total_count = 0
        
        # Usamos el generador nuevo de ispcube.py
        for lote in ispcube.obtener_conexiones_paginadas():
            for c in lote:
                if not c.get("id") or not c.get("user"): continue
                
                direccion = c.get("direccion") or c.get("address")
                
                db.insert_connection(
                    str(c.get("id")), 
                    str(c.get("user")), 
                    str(c.get("customer_id")), 
                    str(c.get("node_id")), 
                    str(c.get("plan_id")), 
                    direccion
                )
                total_count += 1
            db.commit()
            
        print(f"      ✅ Total: {total_count} conexiones guardadas.")
        config.logger.info(f"[SYNC] {total_count} conexiones sincronizadas.")
        db.log_sync_status("ispcube", "ok", f"{total_count} conexiones sincronizadas")

    except Exception as e:
        print(f"      ❌ Error crítico en conexiones: {e}")
        config.logger.error(f"[SYNC] Error Connections: {e}")

def sync_clientes(db):
    print("   ↳ [ISPCube] Bajando Clientes...", end=" ", flush=True)
    try:
        # Asumimos que obtener_clientes ya tiene paginación interna o funciona bien
        clientes = ispcube.obtener_clientes()
        if clientes:
            db.cursor.execute("DELETE FROM clientes")
            db.cursor.execute("DELETE FROM clientes_emails")
            db.cursor.execute("DELETE FROM clientes_telefonos")

            for c in clientes:
                cliente_data = mapear_cliente(c)
                db.insert_cliente(cliente_data)
                insertar_contactos_relacionados(db, c)

            db.commit()
            config.logger.info(f"[SYNC] {len(clientes)} clientes sincronizados.")
            db.log_sync_status("ispcube", "ok", f"{len(clientes)} clientes sincronizados")
            print(f"✅ ({len(clientes)})")
        else:
            print("⚠️ Vacío")
            db.log_sync_status("ispcube", "empty", "Sin datos de clientes")
    except Exception as e:
        print(f"❌ {e}")

# --- UTILIDADES ---

def insertar_contactos_relacionados(db, json_cliente: dict):
    for email_obj in json_cliente.get("contact_emails", []):
        if email_obj.get("email"):
            db.insert_cliente_email(json_cliente["id"], email_obj.get("email"))
    for tel_obj in json_cliente.get("phones", []):
        if tel_obj.get("number"):
            db.insert_cliente_telefono(json_cliente["id"], tel_obj.get("number"))

def mapear_cliente(json_cliente: dict) -> dict:
    return {
        "id": json_cliente.get("id"),
        "code": json_cliente.get("code"),
        "name": json_cliente.get("name"),
        "tax_residence": json_cliente.get("tax_residence"),
        "type": json_cliente.get("type"),
        "tax_situation_id": json_cliente.get("tax_situation_id"),
        "identification_type_id": json_cliente.get("identification_type_id"),
        "doc_number": json_cliente.get("doc_number"),
        "auto_bill_sending": json_cliente.get("auto_bill_sending"),
        "auto_payment_recipe_sending": json_cliente.get("auto_payment_recipe_sending"),
        "nickname": json_cliente.get("nickname"),
        "comercial_activity": json_cliente.get("comercial_activity"),
        "address": json_cliente.get("address"),
        "between_address1": json_cliente.get("between_address1"),
        "between_address2": json_cliente.get("between_address2"),
        "city_id": json_cliente.get("city_id"),
        "lat": json_cliente.get("lat"),
        "lng": json_cliente.get("lng"),
        "extra1": json_cliente.get("extra1"),
        "extra2": json_cliente.get("extra2"),
        "entity_id": json_cliente.get("entity_id"),
        "collector_id": json_cliente.get("collector_id"),
        "seller_id": json_cliente.get("seller_id"),
        "block": json_cliente.get("block"),
        "free": json_cliente.get("free"),
        "apply_late_payment_due": json_cliente.get("apply_late_payment_due"),
        "apply_reconnection": json_cliente.get("apply_reconnection"),
        "contract": json_cliente.get("contract"),
        "contract_type_id": json_cliente.get("contract_type_id"),
        "contract_expiration_date": json_cliente.get("contract_expiration_date"),
        "paycomm": json_cliente.get("paycomm"),
        "expiration_type_id": json_cliente.get("expiration_type_id"),
        "business_id": json_cliente.get("business_id"),
        "first_expiration_date": json_cliente.get("first_expiration_date"),
        "second_expiration_date": json_cliente.get("second_expiration_date"),
        "next_month_corresponding_date": json_cliente.get("next_month_corresponding_date"),
        "start_date": json_cliente.get("start_date"),
        "perception_id": json_cliente.get("perception_id"),
        "phonekey": json_cliente.get("phonekey"),
        "debt": json_cliente.get("debt"),
        "duedebt": json_cliente.get("duedebt"),
        "speed_limited": json_cliente.get("speed_limited"),
        "status": json_cliente.get("status"),
        "enable_date": json_cliente.get("enable_date"),
        "block_date": json_cliente.get("block_date"),
        "created_at": json_cliente.get("created_at"),
        "updated_at": json_cliente.get("updated_at"),
        "deleted_at": json_cliente.get("deleted_at"),
        "temporary": json_cliente.get("temporary"),
    }

# --- MAIN ---

def nightly_sync():
    init_db()
    db = Database()
    print("\n[SYNC] 🚀 Iniciando Sincronización...\n")
    try:
        sync_nodes(db)      # 1. Nodos primero (para tener IPs)
        sync_secrets(db)    # 2. Secrets (ahora sí, por cada nodo)
        sync_onus(db)       # 3. ONUs
        sync_plans(db)      # 4. Planes
        sync_connections(db)# 5. Conexiones (PAGINADO AHORA)
        sync_clientes(db)   # 6. Clientes
        
        print("\n   ↳ Cruzando datos (Match Connections)...", end=" ", flush=True)
        db.match_connections()
        db.commit()
        print("✅ OK")
        
        config.logger.info("[SYNC] Sincronización completa finalizada.")
    finally:
        db.close()
        print("\n[SYNC] ✨ Finalizado.\n")

if __name__ == "__main__":
    nightly_sync()