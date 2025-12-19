from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

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
    nodes = db.get_nodes_for_sync()
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos para sync secrets.")
        return

    db.cursor.execute("DELETE FROM ppp_secrets")
    print(f"   ↳ Consultando {len(nodes)} Mikrotiks:")
    total_secrets = 0

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
                print(f"✅ ({count})")
            else:
                print("⚠️ Sin respuesta")
        except Exception as e:
            print(f"❌ Error: {e}")
            config.logger.error(f"[SYNC] Error en router {ip}: {e}")
    
    db.commit()
    config.logger.info(f"[SYNC] {total_secrets} secrets sincronizados.")
    print(f"   ↳ Resumen: {total_secrets} secrets guardados.")

def sync_onus(db):
    print("   ↳ Consultando SmartOLT...", end=" ", flush=True)
    try:
        onus = smartolt.get_all_onus()
        if onus:
            db.cursor.execute("DELETE FROM subscribers")
            for onu in onus:
                db.insert_subscriber(
                    onu.get("unique_external_id"), onu.get("sn"), onu.get("olt_name"), 
                    onu.get("olt_id"), onu.get("board"), onu.get("port"), onu.get("onu"), 
                    onu.get("onu_type_id"), onu.get("name"), onu.get("mode")
                )
            db.log_sync_status("smartolt", "ok", f"{len(onus)} ONUs sincronizadas")
            config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
            print(f"✅ ({len(onus)} ONUs)")
        else:
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
            print(f"✅ ({len(planes)})")
        else: print("⚠️")
    except Exception as e: print(f"❌ {e}")

def sync_connections(db):
    print("   ↳ [ISPCube] Bajando Conexiones (Lista Completa)...", end=" ", flush=True)
    try:
        # VOLVEMOS AL MÉTODO CLÁSICO
        conexiones = ispcube.obtener_todas_conexiones()
        if conexiones:
            db.cursor.execute("DELETE FROM connections")
            for c in conexiones:
                if not c.get("id") or not c.get("user"): continue
                db.insert_connection(
                    str(c["id"]), str(c["user"]), str(c["customer_id"]), 
                    str(c["node_id"]), str(c["plan_id"]), c.get("direccion")
                )
            config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")
            db.log_sync_status("ispcube", "ok", f"{len(conexiones)} conexiones sincronizadas")
            print(f"✅ ({len(conexiones)})")
        else:
            print("⚠️ Vacío")
    except Exception as e:
        print(f"❌ {e}")
        config.logger.error(f"[SYNC] Error Connections: {e}")

def sync_clientes(db):
    print("   ↳ [ISPCube] Bajando Clientes...", end=" ", flush=True)
    try:
        clientes = ispcube.obtener_clientes()
        if clientes:
            db.cursor.execute("DELETE FROM clientes")
            db.cursor.execute("DELETE FROM clientes_emails")
            db.cursor.execute("DELETE FROM clientes_telefonos")

            for c in clientes:
                db.insert_cliente(mapear_cliente(c))
                insertar_contactos_relacionados(db, c)

            db.commit()
            config.logger.info(f"[SYNC] {len(clientes)} clientes sincronizados.")
            db.log_sync_status("ispcube", "ok", f"{len(clientes)} clientes sincronizados")
            print(f"✅ ({len(clientes)})")
        else:
            print("⚠️ Vacío")
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

def nightly_sync():
    init_db()
    db = Database()
    print("\n[SYNC] 🚀 Iniciando Sincronización...\n")
    try:
        sync_nodes(db)
        sync_secrets(db)
        sync_onus(db)
        sync_plans(db)
        sync_connections(db) # Vuelve a usar el método "todo de una vez"
        sync_clientes(db)
        
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