# app/db/sqlite.py
import sqlite3
from app import config
from datetime import datetime

class Database:
    def __init__(self, path=config.DB_PATH):
        self.conn = sqlite3.connect(path)
        self.cursor = self.conn.cursor()

    # ------------------ INSERTS ------------------

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

    def insert_secret(self, secret_data: dict, router_ip: str):
        self.cursor.execute("""
            INSERT OR REPLACE INTO ppp_secrets (name, password, profile, service, last_caller_id, comment, router_ip, last_logged_out)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            secret_data.get("name"),
            secret_data.get("password"),
            secret_data.get("profile"),
            secret_data.get("service"),
            secret_data.get("last-caller-id"), 
            secret_data.get("comment"),
            router_ip,
            secret_data.get("last-logged-out")
        ))

    # ------------------ UTILIDADES ------------------

    def get_nodes_for_sync(self) -> list:
        self.cursor.execute("SELECT ip_address, puerto, name FROM nodes WHERE ip_address IS NOT NULL AND ip_address != ''")
        rows = self.cursor.fetchall()
        
        nodes = []
        for r in rows:
            nodes.append({
                "ip": r[0],
                "port": int(r[1]) if r[1] and r[1].isdigit() else None,
                "name": r[2]
            })
        return nodes

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

    # ------------------ BÚSQUEDA Y DIAGNÓSTICO ------------------

    def search_client(self, query_str: str) -> list:
        term = f"%{query_str}%"
        sql = """
        SELECT 
            p.name as pppoe,
            COALESCE(cl.name, p.comment, 'No Vinculado') as nombre,
            COALESCE(cl.address, 'SN: ' || IFNULL(s.sn, '?'), p.comment, 'Sin Dirección') as direccion,
            COALESCE(cl.id, 0) as id,
            CASE 
                WHEN cl.id IS NOT NULL THEN 'ispcube'
                WHEN s.unique_external_id IS NOT NULL THEN 'smartolt'
                ELSE 'mikrotik'
            END as origen,
            p.last_caller_id as mac
        FROM ppp_secrets p
        LEFT JOIN connections c ON p.name = c.pppoe_username
        LEFT JOIN clientes cl ON c.customer_id = cl.id
        LEFT JOIN subscribers s ON p.name = s.pppoe_username
        WHERE 
            p.name LIKE ? OR 
            cl.name LIKE ? OR 
            cl.address LIKE ? OR 
            s.sn LIKE ? OR
            p.comment LIKE ? OR
            p.last_caller_id LIKE ?
        LIMIT 20
        """
        self.cursor.execute(sql, (term, term, term, term, term, term))
        rows = self.cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "pppoe": r[0],
                "nombre": r[1],
                "direccion": r[2],
                "id": r[3],
                "origen": r[4],
                "mac": r[5]
            })
        return results

    def get_diagnosis(self, pppoe_user: str) -> dict:
        """
        Obtiene datos para diagnóstico con lógica unificada.
        """
        # 1. INTENTO ADMINISTRATIVO (ISPCube - Camino Feliz)
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
                l.name AS cliente_nombre,
                sec.last_caller_id as mac
        FROM clientes l
        LEFT JOIN connections c ON l.id = c.customer_id
        LEFT JOIN subscribers s ON c.pppoe_username = s.pppoe_username
        LEFT JOIN nodes n ON c.node_id = n.node_id
        LEFT JOIN plans p ON c.plan_id = p.plan_id
        LEFT JOIN ppp_secrets sec ON c.pppoe_username = sec.name
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
                "cliente_nombre": row[10],
                "mac": row[11]
            }

        # 2. INTENTO TÉCNICO UNIFICADO
        
        # A) Buscar en SmartOLT (Subscribers)
        self.cursor.execute("SELECT * FROM subscribers WHERE pppoe_username = ?", (pppoe_user,))
        sub_row = self.cursor.fetchone()
        
        # B) Buscar en Mikrotik (Secrets)
        self.cursor.execute("SELECT * FROM ppp_secrets WHERE name = ?", (pppoe_user,))
        sec_row = self.cursor.fetchone()

        if not sub_row and not sec_row:
             return {"error": f"Cliente {pppoe_user} no encontrado en ninguna base."}

        # C) Armar respuesta combinada
        diagnosis = {
            "cliente_nombre": "No Vinculado",
            "direccion": "N/A",
            "plan": "N/A",
            "pppoe_username": pppoe_user,
            "onu_sn": "N/A",
            "Modo": "N/A",
            "OLT": "N/A",
            "nodo_nombre": "Desconocido",
            "nodo_ip": None,
            "puerto": None,
            "unique_external_id": None,
            "mac": None
        }

        # Llenar datos de SmartOLT si existen
        if sub_row:
            diagnosis["unique_external_id"] = sub_row[0]
            diagnosis["onu_sn"] = sub_row[2]
            diagnosis["OLT"] = sub_row[3]
            diagnosis["Modo"] = sub_row[9]

        # Llenar datos de Secret si existen
        if sec_row:
            diagnosis["mac"] = sec_row[4]
            raw_ip = sec_row[6]
            
            # D) CORRECCIÓN: Usar la IP del secret como PUNTERO a la tabla nodes
            if raw_ip:
                self.cursor.execute("SELECT name, ip_address, puerto FROM nodes WHERE ip_address = ?", (raw_ip,))
                node_row = self.cursor.fetchone()
                
                if node_row:
                    # Encontramos el nodo oficial: Usamos SU configuración (incluyendo puerto)
                    diagnosis["nodo_nombre"] = node_row[0]
                    diagnosis["nodo_ip"] = node_row[1]
                    diagnosis["puerto"] = node_row[2]
                else:
                    # Fallback: No está en tabla nodes, usamos la IP cruda (puerto irá a default)
                    diagnosis["nodo_nombre"] = f"Router {raw_ip}"
                    diagnosis["nodo_ip"] = raw_ip
                    diagnosis["puerto"] = None 

            if sec_row[5]: 
                 diagnosis["direccion"] = f"MK: {sec_row[5]}"

        return diagnosis

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

# ------------------ INICIALIZACIÓN DB ------------------

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    # Tablas existentes (resumido)
    cursor.execute("CREATE TABLE IF NOT EXISTS subscribers (unique_external_id TEXT PRIMARY KEY, pppoe_username TEXT, sn TEXT, olt_name TEXT, olt_id TEXT, board TEXT, port TEXT, onu TEXT, onu_type_id TEXT, mode TEXT, node_id TEXT, connection_id TEXT, vlan TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS nodes (node_id TEXT PRIMARY KEY, name TEXT, ip_address TEXT, puerto TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS plans (plan_id TEXT PRIMARY KEY, name TEXT, speed TEXT, description TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS connections (connection_id TEXT PRIMARY KEY, pppoe_username TEXT, customer_id TEXT, node_id TEXT, plan_id TEXT, direccion TEXT)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT, tax_residence TEXT, type TEXT, tax_situation_id INTEGER, identification_type_id INTEGER, doc_number TEXT, auto_bill_sending INTEGER, auto_payment_recipe_sending INTEGER, nickname TEXT, comercial_activity TEXT, address TEXT, between_address1 TEXT, between_address2 TEXT, city_id INTEGER, lat TEXT, lng TEXT, extra1 TEXT, extra2 TEXT, entity_id INTEGER, collector_id INTEGER, seller_id INTEGER, block INTEGER, free INTEGER, apply_late_payment_due INTEGER, apply_reconnection INTEGER, contract INTEGER, contract_type_id INTEGER, contract_expiration_date TEXT, paycomm TEXT, expiration_type_id INTEGER, business_id INTEGER, first_expiration_date TEXT, second_expiration_date TEXT, next_month_corresponding_date INTEGER, start_date TEXT, perception_id INTEGER, phonekey TEXT, debt TEXT, duedebt TEXT, speed_limited INTEGER, status TEXT, enable_date TEXT, block_date TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT, temporary INTEGER
        )""")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes_emails (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, email TEXT NOT NULL, FOREIGN KEY (customer_id) REFERENCES clientes(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes_telefonos (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, number TEXT NOT NULL, FOREIGN KEY (customer_id) REFERENCES clientes(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS sync_status (id INTEGER PRIMARY KEY AUTOINCREMENT, fuente TEXT NOT NULL, ultima_actualizacion TEXT NOT NULL, estado TEXT NOT NULL, detalle TEXT)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_status_fuente_fecha ON sync_status (fuente, ultima_actualizacion)")

    # Tabla Secrets
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ppp_secrets (
            name TEXT PRIMARY KEY,
            password TEXT,
            profile TEXT,
            service TEXT,
            last_caller_id TEXT,
            comment TEXT,
            router_ip TEXT,
            last_logged_out TEXT
        )
    """)

    conn.commit()
    conn.close()