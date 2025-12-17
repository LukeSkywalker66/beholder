from app.db.sqlite import Database
from app.clients import mikrotik, smartolt, ispcube
from app.config import logger
from app import config # Importar config para fallback

def consultar_diagnostico(pppoe_user: str) -> dict:
    db = Database()
    try:
        # Esto ahora busca en ISPCube primero, luego en SmartOLT
        base = db.get_diagnosis(pppoe_user)
        if "error" in base:
            return base

        diagnosis = base.copy()

        # Mikrotik
        # Si no tenemos nodo_ip (cliente solo en OLT), usamos el default MK_HOST del .env
        router_ip = base.get("nodo_ip")
        if not router_ip:
            logger.warning(f"Sin IP de nodo para {pppoe_user}. Usando MK_HOST por defecto.")
            router_ip = config.MK_HOST

        # Validamos PPPoE (si router_ip es válido)
        if router_ip:
            pppoe_info = mikrotik.validar_pppoe(router_ip, pppoe_user, base.get("puerto", config.MK_PORT))
            diagnosis["mikrotik"] = pppoe_info
        else:
             diagnosis["mikrotik"] = {"active": False, "error": "No Router IP"}

        # SmartOLT (Solo si tenemos unique_external_id)
        external_id = base.get("unique_external_id")
        if external_id:
            diagnosis["onu_status_smrt"] = smartolt.get_onu_status(external_id)
            diagnosis["onu_signal_smrt"] = smartolt.get_onu_signals(external_id)
            diagnosis["onu_vlan"] = smartolt.get_attached_vlans(external_id)
        else:
             # Caso raro: Cliente en ISPCube pero sin ONU vinculada
             diagnosis["onu_status_smrt"] = {"status": False, "error": "Sin ONU asociada"}

        return diagnosis
    except Exception as e:
        logger.exception(f"Error en diagnóstico de {pppoe_user}. Detalles: {e}")
        return diagnosis # Retornamos lo que tengamos
    finally:
        db.close()