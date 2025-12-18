from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
import time

# ==========================================
# FUNCIONES DE SINCRONIZACIÓN
# ==========================================

def sync_nodes(db):
    print("   ↳ Buscando Nodos en ISPCube...", end=" ", flush=True)
    try:
        nodes = ispcube.obtener_nodos()
        if nodes:
            db.cursor.execute("DELETE FROM nodes")
            for n in nodes:
                db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
            db.commit()
            print(f"✅ ({len(nodes)} encontrados)")
            config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")
        else:
            print("⚠️ Lista vacía")
            config.logger.warning("[SYNC] ISPCube devolvió lista de nodos vacía.")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error bajando Nodos: {e}")

def sync_secrets(db):
    nodes = db.get_nodes_for_sync()
    if not nodes:
        print("   ↳ ⚠️ No hay nodos para consultar Mikrotik.")
        return

    # Borramos y regeneramos la foto técnica completa
    db.cursor.execute("DELETE FROM ppp_secrets")
    
    print(f"   ↳ Consultando {len(nodes)} Mikrotiks...", end=" ", flush=True)
    
    count_ok = 0
    total_secrets = 0
    
    for node in nodes:
        ip = node["ip"]
        port = node["port"] if node["port"] else config.MK_PORT
        try:
            secrets = mikrotik.get_all_secrets(ip, port)
            if secrets is not None:
                for s in secrets:
                    db.insert_secret(s, ip) 
                total_secrets += len(secrets)
                count_ok += 1
        except Exception as e:
            config.logger.error(f"[SYNC] Error en router {ip}: {e}")

    db.commit()
    print(f"✅ ({total_secrets} secrets en {count_ok}/{len(nodes)} routers)")
    config.logger.info(f"[SYNC] Secrets sincronizados: {total_secrets}.")

def sync_onus(db):
    print("   ↳ Consultando SmartOLT...", end=" ", flush=True)
    try:
        onus = smartolt.get_all_onus()
        if onus:
            db.cursor.execute("DELETE FROM subscribers")
            for onu in onus:
                db.insert_subscriber(onu.get("unique_external_id"), onu.get("sn"), onu.get("olt_name"), onu.get("olt_id"), onu.get("board"), onu.get("port"), onu.get("onu"), onu.get("onu_type_id"), onu.get("name"), onu.get("mode"))
            db.commit()
            print(f"✅ ({len(onus)} ONUs)")
            config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
        else:
            print("⚠️ Sin datos")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error SmartOLT: {e}")

def sync_administrativos(db):
    # Planes
    print("   ↳ [ISPCube] Bajando Planes...", end=" ", flush=True)
    try:
        planes = ispcube.obtener_planes()
        if planes:
            db.cursor.execute("DELETE FROM plans")
            for p in planes: db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
            db.commit()
            print(f"✅ ({len(planes)})")
        else: print("⚠️")
    except Exception as e: print(f"❌ {e}")

    # Conexiones
    print("   ↳ [ISPCube] Bajando Conexiones...", end=" ", flush=True)
    try:
        conexiones = ispcube.obtener_todas_conexiones()
        if conexiones:
            db.cursor.execute("DELETE FROM connections")
            for c in conexiones: db.insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"], c.get("direccion"))
            db.commit()
            print(f"✅ ({len(conexiones)})")
        else: print("⚠️")
    except Exception as e: print(f"❌ {e}")

    # Clientes
    print("   ↳ [ISPCube] Bajando Clientes (Esto puede tardar)...", end=" ", flush=True)
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
            print(f"✅ ({len(clientes)})")
            config.logger.info(f"[SYNC] {len(clientes)} clientes sincronizados.")
        else:
            print("⚠️ Vacío")
    except Exception as e: 
        print(f"❌ FALLÓ: {e}")
        config.logger.error(f"[SYNC] CRÍTICO: Error bajando Clientes ISPCube: {e}")

def insertar_contactos_relacionados(db, json_cliente: dict):
    for email_obj in json_cliente.get("contact_emails", []):
        if email_obj.get("email"): db.insert_cliente_email(json_cliente["id"], email_obj.get("email"))
    for tel_obj in json_cliente.get("phones", []):
        if tel_obj.get("number"): db.insert_cliente_telefono(json_cliente["id"], tel_obj.get("number"))

# ==========================================
# MAIN
# ==========================================
def nightly_sync():
    init_db()
    db = Database()
    
    print("\n[SYNC] 🚀 Iniciando Sincronización...\n")
    
    # 1. Nodos
    sync_nodes(db)
    
    # 2. Secrets
    sync_secrets(db)
    
    # 3. ONUs
    sync_onus(db)
    
    # 4. Datos Administrativos
    sync_administrativos(db)
    
    # 5. Relacionar
    print("   ↳ Cruzando datos (Match Connections)...", end=" ", flush=True)
    try:
        db.match_connections()
        print("✅ OK")
    except Exception as e:
        print(f"❌ {e}")
    
    db.close()
    print("\n[SYNC] ✨ Finalizado con éxito.\n")

# (Mapeo igual que siempre)
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

if __name__ == "__main__":
    nightly_sync()