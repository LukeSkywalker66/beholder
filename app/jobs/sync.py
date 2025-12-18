from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

def sync_onus(db):
    print("   ↳ Consultando SmartOLT...", end=" ", flush=True)
    try:
        onus = smartolt.get_all_onus()
        if onus:
            db.cursor.execute("DELETE FROM subscribers")
            for onu in onus:
                db.insert_subscriber(
                    onu.get("unique_external_id"), # type: ignore
                    onu.get("sn"), # type: ignore
                    onu.get("olt_name"), # type: ignore
                    onu.get("olt_id"), # type: ignore
                    onu.get("board"), # type: ignore
                    onu.get("port"), # type: ignore
                    onu.get("onu"), # type: ignore
                    onu.get("onu_type_id"), # type: ignore
                    onu.get("name"), # type: ignore
                    onu.get("mode") # type: ignore
                )
            db.log_sync_status("smartolt", "ok", f"{len(onus)} ONUs sincronizadas")
            config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
            print(f"✅ ({len(onus)} ONUs)")
        else:
            db.log_sync_status("smartolt", "empty", "SmartOLT no devolvió datos")
            config.logger.info(f"[SYNC] no se pudo sincronizar ONUs.")
            print("⚠️ Sin datos")
    except Exception as e:
        print(f"❌ Error: {e}")
        config.logger.error(f"[SYNC] Error SmartOLT: {e}")

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
    print("   ↳ [ISPCube] Bajando Conexiones...", end=" ", flush=True)
    try:
        conexiones = ispcube.obtener_todas_conexiones()
        if conexiones:
            db.cursor.execute("DELETE FROM connections")
            for c in conexiones:
                # FIX: Obtenemos dirección de la conexión para búsqueda correcta
                direccion_instalacion = c.get("direccion") or c.get("address")
                db.insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"], direccion_instalacion)
            config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")
            db.log_sync_status("ispcube", "ok", f"{len(conexiones)} conecciones sincronizadas")
            print(f"✅ ({len(conexiones)})")
        else: print("⚠️")
    except Exception as e: print(f"❌ {e}")

def sync_secrets(db):
    # Log detallado paso a paso para identificar nodos fallidos
    nodes = db.get_nodes_for_sync()
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos para sync secrets.")
        print("   ↳ ⚠️ No hay nodos para consultar Mikrotik.")
        return

    # Borramos la tabla para regenerarla limpia
    db.cursor.execute("DELETE FROM ppp_secrets")
    
    print(f"   ↳ Consultando {len(nodes)} Mikrotiks:")
    
    total_secrets = 0
    count_ok = 0

    for node in nodes:
        ip = node["ip"]
        name = node["name"]
        port = node["port"] if node["port"] else config.MK_PORT
        
        # Mensaje de progreso
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
                print("⚠️ Sin respuesta/Vacío")
        except Exception as e:
            print(f"❌ Error: {e}")
            config.logger.error(f"[SYNC] Error en router {ip}: {e}")
    
    db.commit()
    config.logger.info(f"[SYNC] {total_secrets} secrets sincronizados de {count_ok}/{len(nodes)} nodos.")
    print(f"   ↳ Resumen: {total_secrets} secrets guardados.")

def sync_clientes(db):
    print("   ↳ [ISPCube] Bajando Clientes (Paginado)...", end=" ", flush=True)
    try:
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
            config.logger.warning("[SYNC] ISPCube no devolvió clientes")
            db.log_sync_status("ispcube", "empty", "Sin datos de clientes")
            print("⚠️ Vacío")
    except Exception as e:
        print(f"❌ {e}")

def insertar_contactos_relacionados(db, json_cliente: dict):
    for email_obj in json_cliente.get("contact_emails", []):
        if email_obj.get("email"):
            db.insert_cliente_email(json_cliente["id"], email_obj.get("email"))
    for tel_obj in json_cliente.get("phones", []):
        if tel_obj.get("number"):
            db.insert_cliente_telefono(json_cliente["id"], tel_obj.get("number"))

def nightly_sync():
    init_db()
    db = Database()
    print("\n[SYNC] 🚀 Iniciando Sincronización...\n")
    try:
        sync_nodes(db)
        sync_secrets(db)
        sync_onus(db)
        sync_plans(db)
        sync_connections(db)
        sync_clientes(db)
        
        print("   ↳ Cruzando datos (Match Connections)...", end=" ", flush=True)
        db.match_connections()
        db.commit()
        print("✅ OK")
        
        config.logger.info("[SYNC] Sincronización completa finalizada.")
    finally:
        db.close()
        print("\n[SYNC] ✨ Finalizado.\n")

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