from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube
from app import config

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
                onu.get("name"),
                onu.get("mode")
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
        db.insert_node(n["id"], n["name"], n["ip"])
    config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")

def sync_plans(db):
    planes = ispcube.obtener_planes()
    if planes:
        db.cursor.execute("DELETE FROM plans")  # Limpia la tabla antes de insertar 
    for p in planes:
        db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
    config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")

def sync_connections(db):
    conexiones = ispcube.obtener_todas_conexiones()
    if conexiones:
        db.cursor.execute("DELETE FROM connections")  # Limpia la tabla antes de insertar
    for c in conexiones:
        db.insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"], c.get("direccion"))
    config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")

def nightly_sync():
    init_db()  # asegura el esquema antes de cualquier operación
    db = Database()
    try:
        sync_onus(db)
        sync_nodes(db)
        sync_plans(db)
        sync_connections(db)
        db.match_connections()
        db.commit()
        config.logger.info("[SYNC] Base actualizada y relaciones PPPoE → node_id → connection_id completadas.")
    finally:
        db.close()
if __name__ == "__main__":
    try:
        nightly_sync()
    except Exception as e:
        print(f"[ERROR] Falló la sincronización: {e}")