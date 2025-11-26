from app.db.sqlite import Database
from app.clients import mikrotik, smartolt, ispcube

def consultar_diagnostico(pppoe_user):
    db = Database()
    try:
        base = db.get_diagnosis_base(pppoe_user)
        if not base:
            return {"error": f"Cliente {pppoe_user} no encontrado"}
        
        diagnosis = base.copy()

        # Mikrotik
        active = mikrotik.get_active_connection(pppoe_user)
        if active:
            diagnosis["pppoe_active"] = True
        else:
            diagnosis["pppoe_active"] = False
            secret_info = mikrotik.get_secret_info(pppoe_user)
            diagnosis["last_disconnect"] = secret_info.get("last_disconnect")
            diagnosis["disconnect_reason"] = secret_info.get("reason")

        # SmartOLT
        diagnosis["onu_status"] = smartolt.get_onu_status(base["unique_external_id"])
        diagnosis["onu_signal"] = smartolt.get_onu_signal(base["unique_external_id"])

        # ISPCube
        conn_info = ispcube.obtener_conexion_por_pppoe(pppoe_user)
        diagnosis["ispcube_status"] = conn_info.get("status")

        plan = ispcube.obtener_plan(base["plan_id"])
        diagnosis["plan"] = plan.get("name")
        diagnosis["speed"] = plan.get("speed")

        return diagnosis
    finally:
        db.close()