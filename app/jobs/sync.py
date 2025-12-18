from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

# ==========================================
# FUNCIONES DE SINCRONIZACIÓN (BLINDADAS)
# ==========================================

def sync_nodes(db):
    """Paso 1: Traer la topología de red desde ISPCube."""
    config.logger.info("[SYNC] Obteniendo nodos...")
    try:
        nodes = ispcube.obtener_nodos()
        if nodes:
            db.cursor.execute("DELETE FROM nodes")
            for n in nodes:
                db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
            db.commit()
            config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")
            db.log_sync_status("ispcube_nodes", "ok", f"{len(nodes)} nodos")
        else:
            config.logger.warning("[SYNC] ISPCube devolvió lista de nodos vacía (manteniendo anteriores).")
    except Exception as e:
        config.logger.error(f"[SYNC] Error bajando Nodos: {e}")
        db.log_sync_status("ispcube_nodes", "error", str(e))

def sync_secrets(db):
    """Paso 2: Iterar sobre los nodos y bajar los secrets de cada Mikrotik."""
    nodes = db.get_nodes_for_sync()
    
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos en la BD para sincronizar secrets.")
        return

    # IMPORTANTE: Aquí sí borramos todo antes de empezar, porque vamos a regenerar
    # la foto completa de la red técnica.
    db.cursor.execute("DELETE FROM ppp_secrets")
    
    total_secrets = 0
    routers_ok = 0
    routers_fail = 0

    print(f"[SYNC] Iniciando descarga de secrets de {len(nodes)} nodos...")

    for node in nodes:
        ip = node["ip"]
        port = node["port"] if node["port"] else config.MK_PORT
        
        try:
            # Timeout corto por si un nodo está apagado, que no frene todo
            secrets = mikrotik.get_all_secrets(ip, port)
            
            if secrets is not None: # Puede ser lista vacía pero válida
                for s in secrets:
                    # insert_secret ahora maneja la PK compuesta (name, router_ip)
                    db.insert_secret(s, ip)
                
                count = len(secrets)
                total_secrets += count
                routers_ok += 1
                # config.logger.info(f"[SYNC] Nodo {ip}: {count} secrets.")
            else:
                config.logger.warning(f"[SYNC] Router {node['name']} ({ip}) no respondió.")
                routers_fail += 1
        except Exception as e:
            routers_fail += 1
            config.logger.error(f"[SYNC] Falló sync con router {ip}: {e}")

    db.commit()
    msg = f"{total_secrets} secrets bajados de {routers_ok} routers ({routers_fail} fallidos)."
    config.logger.info(f"[SYNC] {msg}")
    db.log_sync_status("mikrotik", "ok", msg)

def sync_onus(db):
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
            db.commit()
            config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
            db.log_sync_status("smartolt", "ok", f"{len(onus)} ONUs")
        else:
            config.logger.warning("[SYNC] SmartOLT devolvió 0 ONUs.")
    except Exception as e:
        config.logger.error(f"[SYNC] Error SmartOLT: {e}")
        db.log_sync_status("smartolt", "error", str(e))

def sync_plans(db):
    try:
        planes = ispcube.obtener_planes()
        if planes:
            db.cursor.execute("DELETE FROM plans")
            for p in planes:
                db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
            db.commit()
            config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")
    except Exception as e:
        config.logger.error(f"[SYNC] Error Planes ISPCube: {e}")

def sync_connections(db):
    try:
        conexiones = ispcube.obtener_todas_conexiones()
        if conexiones:
            db.cursor.execute("DELETE FROM connections")
            for c in conexiones:
                db.insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"], c.get("direccion"))
            db.commit()
            config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")
            db.log_sync_status("ispcube_conn", "ok", f"{len(conexiones)} conexiones")
    except Exception as e:
        config.logger.error(f"[SYNC] Error Conexiones ISPCube: {e}")
        # No borramos datos viejos si falla

def sync_clientes(db):
    try:
        # Aquí suele dar el Timeout 524 si hay muchos clientes
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
            db.log_sync_status("ispcube_clients", "ok", f"{len(clientes)} clientes")
        else:
            config.logger.warning("[SYNC] ISPCube devolvió lista vacía de clientes.")
    except Exception as e:
        config.logger.error(f"[SYNC] CRÍTICO: Error bajando Clientes ISPCube: {e}")
        db.log_sync_status("ispcube_clients", "error", str(e))
        # IMPORTANTE: No hacemos raise, dejamos que el script siga para tener al menos los secrets

def insertar_contactos_relacionados(db, json_cliente: dict):
    for email_obj in json_cliente.get("contact_emails", []):
        email = email_obj.get("email")
        if email:
            db.insert_cliente_email(json_cliente["id"], email)

    for tel_obj in json_cliente.get("phones", []):
        number = tel_obj.get("number")
        if number:
            db.insert_cliente_telefono(json_cliente["id"], number)

#------------------
# LÓGICA PRINCIPAL
#------------------
def nightly_sync():
    init_db()  # Asegura esquema y crea índices si faltan
    db = Database()
    
    print("[SYNC] Iniciando proceso de sincronización...")
    
    # Ejecutamos en orden, pero si uno falla, los otros siguen.
    
    # 1. Nodos (Fundamental)
    sync_nodes(db)
    
    # 2. Secrets (La verdad técnica - Mikrotik)
    sync_secrets(db)
    
    # 3. ONUs (La verdad física - SmartOLT)
    sync_onus(db)
    
    # 4. Datos Administrativos (ISPCube) - Estos suelen fallar por timeout
    sync_plans(db)
    sync_connections(db)
    sync_clientes(db) 
    
    # 5. Relacionar todo (Finalización)
    try:
        db.match_connections()
        print("[SYNC] Relaciones actualizadas (match_connections).")
    except Exception as e:
        config.logger.error(f"[SYNC] Error en match_connections: {e}")

    db.close()
    print("[SYNC] Proceso finalizado.")

#------------------ Funciones de mapeo (Sin cambios) ------------------
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
    # El try/except global solo atrapa errores catastróficos de inicialización
    try:
        nightly_sync()
    except Exception as e:
        print(f"[ERROR FATAL] Falló el script de sincronización: {e}")