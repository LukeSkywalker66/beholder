from app.clients import smartolt, ispcube
from app import config
from app.db.sqlite import insert_subscriber, insert_node, insert_connection, match_connections, insert_plan

def sync_onus():
    onus = smartolt.get_all_onus()
    for onu in onus:
        insert_subscriber(
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


def sync_nodes():
    nodes = ispcube.obtener_nodos()
    for node in nodes:
        insert_node(node["id"], node["name"], node["ip"])
    config.logger.info(f"[SYNC] {len(nodes)} nodos sincronizados.")

def sync_plans():
    planes = ispcube.obtener_planes()
    for p in planes:
        insert_plan(p["id"], p["name"], p.get("speed"), p.get("comment"))
    config.logger.info(f"[SYNC] {len(planes)} planes sincronizados.")

def sync_connections():
    conexiones = ispcube.obtener_todas_conexiones()
    for c in conexiones:
        insert_connection(c["id"], c["user"], c["customer_id"], c["node_id"], c["plan_id"])
    config.logger.info(f"[SYNC] {len(conexiones)} conexiones sincronizadas.")

def nightly_sync():
    sync_onus()
    sync_nodes()
    sync_connections()
    match_connections()
    config.logger.info("[SYNC] Base actualizada y relaciones PPPoE → node_id → connection_id completadas.")

if __name__ == "__main__":
    try:
        nightly_sync()
    except Exception as e:
        print(f"[ERROR] Falló la sincronización: {e}")