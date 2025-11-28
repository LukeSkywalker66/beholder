from app.db.sqlite import Database
from app.clients import mikrotik, smartolt, ispcube
from app.config import logger


def consultar_diagnostico(pppoe_user: str) -> dict:
    db = Database()
    try:
        base = db.get_diagnosis(pppoe_user)
        if "error" in base:
            return base

        diagnosis = base.copy()

        # Mikrotik → validación PPPoE usando nodo_ip
        pppoe_info = mikrotik.validar_pppoe(base["nodo_ip"], pppoe_user)
        if pppoe_info.get("active"):
            diagnosis["pppoe_active"] = True
        else:
            diagnosis["pppoe_active"] = False
            diagnosis["last_disconnect"] = pppoe_info.get("last_disconnect")
            diagnosis["disconnect_reason"] = pppoe_info.get("reason")

        # SmartOLT
        diagnosis["onu_status"] = smartolt.get_onu_status(base["unique_external_id"])
        diagnosis["onu_signal"] = smartolt.get_onu_signals(base["unique_external_id"])

        # ISPCube
        # conn_info = ispcube.obtener_conexion_por_pppoe(pppoe_user)
        # diagnosis["ispcube_status"] = conn_info.get("status")

        # plan = ispcube.obtener_plan(conn_info.get("plan_id"))
        # diagnosis["plan"] = plan.get("name")
        # diagnosis["speed"] = plan.get("speed")

        return diagnosis
    finally:
        db.close()