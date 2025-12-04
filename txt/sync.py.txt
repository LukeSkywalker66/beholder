from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube
from app import config
from app.utils.safe_call import safe_call


def sync_onus(db):
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
    else:
        db.log_sync_status("smartolt", "empty", "SmartOLT no devolvió datos, se mantienen registros anteriores")
        config.logger.info(f"[SYNC] no se pudo sincronizar ONUs.")


def sync_nodes(db):
    nodes = ispcube.obtener_nodos()
    if nodes:
        db.cursor.execute("DELETE FROM nodes")  # Limpia la tabla antes de insertar
    for n in nodes:
        db.insert_node(n["id"], n["name"], n["ip"], n["puerto"])
    config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")
    db.log_sync_status("ispcube", "ok", f"{len(nodes)} nodos sincronizadas")


def sync_plans(db):
    planes = ispcube.obtener_planes()
    if planes:
        db.cursor.execute("DELETE FROM plans")  # Limpia la tabla antes de insertar 
    for p in planes:
        db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
    config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")
    db.log_sync_status("ispcube", "ok", f"{len(planes)} planes sincronizadas")


def sync_connections(db):
    conexiones = ispcube.obtener_todas_conexiones()
    if conexiones:
        db.cursor.execute("DELETE FROM connections")  # Limpia la tabla antes de insertar
    for c in conexiones:
        db.insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"], c.get("direccion"))
    config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")
    db.log_sync_status("ispcube", "ok", f"{len(conexiones)} conecciones sincronizadas")

def sync_clientes(db):
    clientes = ispcube.obtener_clientes()  # debe devolver la lista completa cruda del endpoint
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
        db.log_sync_status("ispcube", "empty", "Sin datos de clientes")

def insertar_contactos_relacionados(db, json_cliente: dict):
    # Emails
    for email_obj in json_cliente.get("contact_emails", []):
        email = email_obj.get("email")
        if email:
            db.insert_cliente_email(json_cliente["id"], email)

    # Teléfonos
    for tel_obj in json_cliente.get("phones", []):
        number = tel_obj.get("number")
        if number:
            db.insert_cliente_telefono(json_cliente["id"], number)

def nightly_sync():
    init_db()  # asegura el esquema antes de cualquier operación
    db = Database()
    try:
        sync_onus(db)
        sync_clientes(db)
        sync_nodes(db)
        sync_plans(db)
        sync_connections(db)
        db.match_connections()
        db.commit()
        config.logger.info("[SYNC] Base actualizada y relaciones PPPoE → node_id → connection_id completadas.")
        print("[SYNC] Base actualizada y relaciones PPPoE → node_id → connection_id completadas.")
    finally:
        db.close()


#------------------ Funciones de mapeo ------------------
#------------------
def mapear_cliente(json_cliente: dict) -> dict:
    """
    Convierte el JSON de ISPCube en un dict compatible con la tabla clientes.
    Incluye casi todos los campos del ejemplo.
    """
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
#------------------

if __name__ == "__main__":
    try:
        nightly_sync()
    except Exception as e:
        print(f"[ERROR] Falló la sincronización: {e}")

