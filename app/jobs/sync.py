from app.db.sqlite import Database, init_db
from app.clients import smartolt, ispcube
from app import config

def sync_onus(db):
    onus = smartolt.get_all_onus()
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
    config.logger.info(f"[SYNC] {len(onus)} ONUs sincronizadas.")

def sync_nodes(db):
    nodes = ispcube.obtener_nodos()
    for n in nodes:
        db.insert_node(n["id"], n["name"], n["ip"])
    config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")

def sync_plans(db):
    planes = ispcube.obtener_planes()
    for p in planes:
        db.insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
    config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")

def sync_connections(db):
    conexiones = ispcube.obtener_todas_conexiones()
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