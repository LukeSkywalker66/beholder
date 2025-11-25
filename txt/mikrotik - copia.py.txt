import logging
import time

from routeros_api import RouterOsApiPool

from app import config

# Credenciales comunes para todos los Mikrotik
MIKROTIK_USER = config.MK_USER
MIKROTIK_PASS = config.MK_PASS
MIKROTIK_PORT = config.MK_PORT   # 👈 tu puerto personalizado
MIKROTIK_IP   = config.MK_HOST  

#Nota para producción: borrar =MIKROTIK_IP y pasar IP como parámetro en cada función

def _connect(router_ip=MIKROTIK_IP, username=MIKROTIK_USER, password=MIKROTIK_PASS, port=MIKROTIK_PORT):
    pool = RouterOsApiPool(
        router_ip,
        username=username,
        password=password,
        port=port,              
        plaintext_login=True
    )
    return pool, pool.get_api()


def obtener_secret(router_ip, pppoe_user): #MIKROTIK_IP, router_ip
    pool, api = _connect(router_ip)
    secrets = api.get_resource('/ppp/secret')
    result = secrets.get(name=pppoe_user)
    pool.disconnect()
    if not result:
        raise RuntimeError(f"Secret {pppoe_user} no encontrado en {router_ip}")
    return result[0]

def crear_secret(router_ip, datos_secret):
    pool, api = _connect(router_ip)
    secrets = api.get_resource('/ppp/secret')
    secrets.add(
        name=datos_secret['name'] + "R", # Borrar la "R" para producción
        password=datos_secret['password'],
        profile=datos_secret.get('profile', 'default'),
        service=datos_secret.get('service', 'pppoe')
    )
    pool.disconnect()
    logging.info(f"Secret {datos_secret['name']} creado en {router_ip}")

def borrar_secret(router_ip, pppoe_user):
    pool, api = _connect(router_ip)
    secrets = api.get_resource('/ppp/secret')
    result = secrets.get(name=pppoe_user)
    if result:
        secret = result[0]
        secret_id = secret.get('.id') or secret.get('id')

        #id=result[0]['.id']
        secrets.remove(id=secret_id)
        logging.info(f"Secret {pppoe_user} eliminado de {router_ip}")
    pool.disconnect()

def migrar_secret(origen_ip, destino_ip, pppoe_user):
    origen_ip = MIKROTIK_IP #borrar para producción
    destino_ip = MIKROTIK_IP #borrar para producción

    datos = obtener_secret(origen_ip, pppoe_user)


    crear_secret(destino_ip, datos)
    # Validación inicial
    if not validar_pppoe(destino_ip, pppoe_user):
        logging.info(f"Esperando 60s para revalidar {pppoe_user} en {destino_ip}...")
        time.sleep(60)

        # Segundo intento
        if not validar_pppoe(destino_ip, pppoe_user):
            logging.error(f"❌ {pppoe_user} no levantó en {destino_ip}, rollback.")
            #borrar_secret(destino_ip, pppoe_user)
            return False

    # Si llegó acá, está online → borrar en origen
    borrar_secret(origen_ip, pppoe_user)
    logging.info(f"✅ {pppoe_user} migrado de {origen_ip} a {destino_ip}")
    return True


def rollback_secret(origen_ip, destino_ip, pppoe_user):
    
    origen_ip = MIKROTIK_IP #borrar para producción
    destino_ip = MIKROTIK_IP #borrar para producción

    datos = obtener_secret(destino_ip, pppoe_user)
    crear_secret(origen_ip, datos)
    borrar_secret(destino_ip, pppoe_user)
    return True

def validar_pppoe(router_ip, pppoe_user):
    
    router_ip = MIKROTIK_IP #borrar para producción

    pool, api = _connect(router_ip)
    activos = api.get_resource('/ppp/active')
    result = activos.get(name=pppoe_user)
    pool.disconnect()
    if result:
        logging.info(f"PPP user {pppoe_user} activo en {router_ip}")
        return True
    logging.warning(f"PPP user {pppoe_user} NO activo en {router_ip}")
    return False