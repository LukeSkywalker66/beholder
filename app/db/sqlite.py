# app/db/sqlite.py
import sqlite3
from app import config
from datetime import datetime

class Database:
    def __init__(self, path=config.DB_PATH):
        self.conn = sqlite3.connect(path)
        self.cursor = self.conn.cursor()

    # ... (Los métodos insert_* y log_sync_status quedan igual, los omito para brevedad si ya los tenés, 
    # pero asegurate de mantener insert_subscriber, insert_node, etc.) ...
    
    def insert_subscriber(self, unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode):
        self.cursor.execute("""
            INSERT OR REPLACE INTO subscribers (
                unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, pppoe_username, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode))

    def insert_node(self, node_id, name, ip_address, puerto):
        self.cursor.execute("""
            INSERT OR REPLACE INTO nodes (node_id, name, ip_address, puerto)
            VALUES (?, ?, ?, ?)
        """, (node_id, name, ip_address, puerto))

    def insert_plan(self, plan_id, name, speed, description):
        self.cursor.execute("""
            INSERT OR REPLACE INTO plans (plan_id, name, speed, description)
            VALUES (?, ?, ?, ?)
        """, (plan_id, name, speed, description))

    def insert_connection(self, connection_id, pppoe_username, customer_id, node_id, plan_id, direccion=None):
        self.cursor.execute("""
            INSERT OR REPLACE INTO connections (connection_id, pppoe_username, customer_id, node_id, plan_id, direccion)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (connection_id, pppoe_username, customer_id, node_id, plan_id, direccion))

    def insert_cliente(self, cliente_data: dict):
        columns = ', '.join(cliente_data.keys())
        placeholders = ', '.join('?' for _ in cliente_data)
        values = tuple(cliente_data.values())
        self.cursor.execute(f"""
            INSERT OR REPLACE INTO clientes ({columns})
            VALUES ({placeholders})
        """, values)
    
    def insert_cliente_email(self, customer_id: int, email: str):
        self.cursor.execute("INSERT INTO clientes_emails (customer_id, email) VALUES (?, ?)", (customer_id, email))
    
    def insert_cliente_telefono(self, customer_id: int, number: str):
        self.cursor.execute("INSERT INTO clientes_telefonos (customer_id, number) VALUES (?, ?)", (customer_id, number))
    
    def match_connections(self):
        self.cursor.execute("""
            UPDATE subscribers
            SET node_id = (
                SELECT node_id FROM connections
                WHERE connections.pppoe_username = subscribers.pppoe_username
            ),
            connection_id = (
                SELECT connection_id FROM connections
                WHERE connections.pppoe_username = subscribers.pppoe_username
            )
        """)
        self.commit()
    
    def log_sync_status(self, fuente: str, estado: str, detalle: str = ""):
        self.cursor.execute("""
            INSERT INTO sync_status (fuente, ultima_actualizacion, estado, detalle)
            VALUES (?, ?, ?, ?)
        """, (fuente, datetime.now(), estado, detalle))
        self.commit()

    # --- NUEVOS MÉTODOS Y REFACTORIZACIÓN ---

    def search_client(self, query_str: str) -> list:
        """
        Busca clientes en ISPCube (administrativo) Y SmartOLT (técnico).
        Usa UNION. Corregido: subscribers no tiene columna name.
        """
        term = f"%{query_str}%"
        
        sql = """
        SELECT 
            c.pppoe_username, 
            cl.name, 
            cl.address, 
            cl.id,
            'ispcube' as source
        FROM clientes cl
        JOIN connections c ON cl.id = c.customer_id
        WHERE 
            cl.name LIKE ? OR 
            cl.address LIKE ? OR 
            c.pppoe_username LIKE ? OR
            cl.doc_number LIKE ?

        UNION

        SELECT 
            s.pppoe_username, 
            'Cliente Técnico (OLT)' as name, 
            'SN: ' || s.sn as address, 
            0 as id,
            'smartolt' as source
        FROM subscribers s
        WHERE 
            s.pppoe_username LIKE ? OR
            s.sn LIKE ?
        """
        
        # 4 parámetros para la primera parte, 2 para la segunda
        self.cursor.execute(sql, (term, term, term, term, term, term))
        rows = self.cursor.fetchall()
        
        results = []
        vistos = set()

        for r in rows:
            pppoe = r[0]
            # Filtramos si el pppoe es nulo o ya lo vimos
            if not pppoe or pppoe in vistos:
                continue
            vistos.add(pppoe)

            results.append({
                "pppoe": pppoe,
                "nombre": r[1],
                "direccion": r[2],
                "id": r[3],
                "origen": r[4]
            })
            
        return results[:20]

    def get_diagnosis(self, pppoe_user: str) -> dict:
        """
        Obtiene datos para diagnóstico.
        Intenta primero el camino completo (ISPCube + SmartOLT).
        Si falla, hace fallback a solo SmartOLT (Subscribers).
        """
        
        # 1. Intento Administrativo + Técnico (El original)
        query_full = """
        SELECT s.unique_external_id,
                s.pppoe_username,
                s.sn AS onu_sn,
                s.mode as Modo,
                s.olt_name AS OLT,
                n.name AS nodo_nombre,
                n.ip_address AS nodo_ip,
                n.puerto AS puerto,
                p.name AS plan,
                c.direccion AS direccion,
                l.name AS cliente_nombre
        FROM clientes l
        LEFT JOIN connections c ON l.id = c.customer_id
        LEFT JOIN subscribers s ON c.pppoe_username = s.pppoe_username
        LEFT JOIN nodes n ON c.node_id = n.node_id
        LEFT JOIN plans p ON c.plan_id = p.plan_id
        WHERE c.pppoe_username = ?
        """
        self.cursor.execute(query_full, (pppoe_user,))
        row = self.cursor.fetchone()

        if row:
            return {
                "unique_external_id": row[0],
                "pppoe_username": row[1],
                "onu_sn": row[2],
                "Modo": row[3],
                "OLT": row[4],
                "nodo_nombre": row[5],
                "nodo_ip": row[6],
                "puerto": row[7],
                "plan": row[8],
                "direccion": row[9],
                "cliente_nombre": row[10]
            }

        # 2. Fallback: Solo Técnico (SmartOLT)
        # Si llegamos acá, es porque no estaba en connections (ISPCube)
        query_tech = """
        SELECT unique_external_id, pppoe_username, sn, mode, olt_name, name
        FROM subscribers
        WHERE pppoe_username = ?
        """
        self.cursor.execute(query_tech, (pppoe_user,))
        row_tech = self.cursor.fetchone()

        if row_tech:
            return {
                "unique_external_id": row_tech[0],
                "pppoe_username": row_tech[1],
                "onu_sn": row_tech[2],
                "Modo": row_tech[3],
                "OLT": row_tech[4],
                "nodo_nombre": "Desconocido (Solo OLT)",
                "nodo_ip": None, # Importante: No tenemos IP del nodo
                "puerto": None,
                "plan": "N/A",
                "direccion": "N/A",
                "cliente_nombre": row_tech[5] or "Sin Nombre en OLT"
            }

        # 3. Si no está ni en la OLT ni en el CRM, devolvemos error
        return {"error": f"Cliente {pppoe_user} no encontrado en ninguna base."}

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

# ... (init_db y demás funciones auxiliares se mantienen igual) ...