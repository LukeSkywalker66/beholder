from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube, mikrotik
from app import config
from app.utils.safe_call import safe_call
import time

def sync_nodes(db):
    """Paso 1: Traer la topología de red desde ISPCube."""
    nodes = ispcube.obtener_nodos()
    if nodes:
        db.cursor.execute("DELETE FROM nodes")
        for n in nodes:
            db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
        db.commit() # Importante commitear acá para que el paso siguiente pueda leerlos
        config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")
        db.log_sync_status("ispcube", "ok", f"{len(nodes)} nodos sincronizados")
    else:
        config.logger.warning("[SYNC] ISPCube no devolvió nodos.")

def sync_secrets(db):
    """Paso 2: Iterar sobre los nodos y bajar los secrets de cada Mikrotik."""
    nodes = db.get_nodes_for_sync()
    
    if not nodes:
        config.logger.warning("[SYNC] No hay nodos en la BD para sincronizar secrets.")
        return

    # Limpiamos la tabla de secrets antes de empezar el barrido masivo
    db.cursor.execute("DELETE FROM ppp_secrets")
    
    total_secrets = 0
    routers_ok = 0
    routers_fail = 0

    print(f"[SYNC] Iniciando descarga de secrets de {len(nodes)} nodos...")

    for node in nodes:
        ip = node["ip"]
        # Si el puerto viene nulo de ISPCube, usamos el default del .env
        port = node["port"] if node["port"] else config.MK_PORT
        
        try:
            secrets = mikrotik.get_all_secrets(ip, port)
            if secrets:
                for s in secrets:
                    db.insert_secret(s, ip)
                total_secrets += len(secrets)
                routers_ok += 1
            else:
                # Puede ser lista vacía (sin secrets) o error de conexión controlado
                config.logger.warning(f"[SYNC] Router {node['name']} ({ip}) devolvió 0 secrets.")
        except Exception as e:
            routers_fail += 1
            config.logger.error(f"[SYNC] Falló sync con router {ip}: {e}")

    db.commit()
    msg = f"{total_secrets} secrets bajados de {routers_ok} routers ({routers_fail} fallidos)."
    config.logger.info(f"[SYNC] {msg}")
    db.log_sync_status("mikrotik", "ok", msg)

def sync_onus(db):
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
                onu.get("name"), # Se guarda en pppoe_username
                onu.get("mode")
            )
        db.log_sync_status("smartolt", "ok", f"{len(onus)} ONUs sincronizadas")
        config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")
    else:
        db.log_sync_status("smartolt", "empty", "SmartOLT no devolvió datos")

def sync_plans(db):
    planes = ispcube.obtener_planes()
    if planes:
        db.cursor.execute("DELETE FROM plans")
    for p in planes:
        db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
    config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")
    db.log_sync_status("ispcube", "ok", f"{len(planes)} planes sincronizados")

def sync_connections(db):
    conexiones = ispcube.obtener_todas_conexiones()
    if conexiones:
        db.cursor.execute("DELETE FROM connections")
    for c in conexiones:
        db.insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"], c.get("direccion"))
    config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")
    db.log_sync_status("ispcube", "ok", f"{len(conexiones)} conexiones sincronizadas")

def sync_clientes(db):
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
    else:
        config.logger.warning("[SYNC] ISPCube no devolvió clientes")

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
    init_db()  # Asegura esquema
    db = Database()
    try:
        print("[SYNC] Iniciando sincronización...")
        
        # 1. Nodos (Fundamental para saber a qué Mikrotiks conectar)
        sync_nodes(db)
        
        # 2. Secrets (La verdad técnica desde los Mikrotiks)
        sync_secrets(db)
        
        # 3. ONUs (La verdad física)
        sync_onus(db)
        
        # 4. Datos Administrativos
        sync_plans(db)
        sync_connections(db)
        sync_clientes(db)
        
        # 5. Relacionar todo
        db.match_connections()
        db.commit()
        
        config.logger.info("[SYNC] Sincronización completa.")
        print("[SYNC] Finalizado con éxito.")
    finally:
        db.close()

#------------------ Funciones de mapeo ------------------
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
    try:
        nightly_sync()
    except Exception as e:
        print(f"[ERROR] Falló la sincronización: {e}")