from db.sqlite import insert_subscriber
from services.smartolt import get_all_onus

def sync_onus():
    onus = get_all_onus()
    count = 0
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
        count += 1
    print(f"[SYNC] {count} ONUs sincronizadas.")


if __name__ == "__main__":
    try:
        sync_onus()
    except Exception as e:
        print(f"[ERROR] Falló la sincronización: {e}")