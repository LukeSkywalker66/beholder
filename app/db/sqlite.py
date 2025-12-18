import sqlite3
from app import config
from datetime import datetime

class Database:
    def __init__(self, path=config.DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    # ------------------ INSERTS (Mantenemos los simples) ------------------
    def insert_subscriber(self, unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode):
        self.cursor.execute("INSERT OR REPLACE INTO subscribers (unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, pppoe_username, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode))
    
    def insert_node(self, node_id, name, ip_address, puerto):
        self.cursor.execute("INSERT OR REPLACE INTO nodes (node_id, name, ip_address, puerto) VALUES (?, ?, ?, ?)", (node_id, name, ip_address, puerto))
    
    def insert_plan(self, plan_id, name, speed, description):
        self.cursor.execute("INSERT OR REPLACE INTO plans (plan_id, name, speed, description) VALUES (?, ?, ?, ?)", (plan_id, name, speed, description))
    
    def insert_connection(self, connection_id, pppoe_username, customer_id, node_id, plan_id, direccion=None):
        self.cursor.execute("INSERT OR REPLACE INTO connections (connection_id, pppoe_username, customer_id, node_id, plan_id, direccion) VALUES (?, ?, ?, ?, ?, ?)", (connection_id, pppoe_username, customer_id, node_id, plan_id, direccion))
    
    def insert_cliente(self, cliente_data: dict):
        columns = ', '.join(cliente_data.keys()); placeholders = ', '.join('?' for _ in cliente_data); values = tuple(cliente_data.values())
        self.cursor.execute(f"INSERT OR REPLACE INTO clientes ({columns}) VALUES ({placeholders})", values)
    
    def insert_cliente_email(self, customer_id: int, email: str):
        self.cursor.execute("INSERT INTO clientes_emails (customer_id, email) VALUES (?, ?)", (customer_id, email))
    
    def insert_cliente_telefono(self, customer_id: int, number: str):
        self.cursor.execute("INSERT INTO clientes_telefonos (customer_id, number) VALUES (?, ?)", (customer_id, number))

    def insert_secret(self, secret_data: dict, router_ip: str):
        # Insert simple, sin complicaciones
        self.cursor.execute("""
            INSERT OR REPLACE INTO ppp_secrets (name, password, profile, service, last_caller_id, comment, router_ip, last_logged_out)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            secret_data.get("name"), secret_data.get("password"), secret_data.get("profile"), secret_data.get("service"),
            secret_data.get("last-caller-id"), secret_data.get("comment"), router_ip, secret_data.get("last-logged-out")
        ))

    # ------------------ UTILIDADES ------------------
    def get_nodes_for_sync(self) -> list:
        self.cursor.execute("SELECT ip_address, puerto, name FROM nodes WHERE ip_address IS NOT NULL AND ip_address != ''")
        return [{"ip": r[0], "port": int(r[1]) if r[1] and r[1].isdigit() else None, "name": r[2]} for r in self.cursor.fetchall()]

    def match_connections(self):
        self.cursor.execute("UPDATE subscribers SET node_id = (SELECT node_id FROM connections WHERE connections.pppoe_username = subscribers.pppoe_username), connection_id = (SELECT connection_id FROM connections WHERE connections.pppoe_username = subscribers.pppoe_username)")
        self.commit()
    
    def log_sync_status(self, fuente: str, estado: str, detalle: str = ""):
        self.cursor.execute("INSERT INTO sync_status (fuente, ultima_actualizacion, estado, detalle) VALUES (?, ?, ?, ?)", (fuente, datetime.now(), estado, detalle)); self.commit()

    # ------------------ BÚSQUEDA OPTIMIZADA (UNION) ------------------
    def search_client(self, query_str: str) -> list:
        term = f"%{query_str}%"
        
        # Esta query ejecuta 3 búsquedas indexadas por separado y une los resultados.
        # Es muchísimo más rápida que hacer un JOIN de todo con OR.
        sql = """
        -- 1. ISPCube
        SELECT 
            c.pppoe_username as pppoe,
            cl.name as nombre,
            cl.address as direccion,
            cl.id as id,
            'ispcube' as origen,
            '' as mac
        FROM clientes cl
        JOIN connections c ON cl.id = c.customer_id
        WHERE cl.name LIKE ? OR cl.address LIKE ? OR c.pppoe_username LIKE ?

        UNION ALL

        -- 2. Mikrotik (Secrets)
        SELECT 
            name as pppoe,
            'No Vinculado' as nombre,
            CASE WHEN comment IS NOT NULL AND comment != '' THEN 'MK: ' || comment ELSE 'Sin Dirección' END as direccion,
            0 as id,
            'mikrotik' as origen,
            last_caller_id as mac
        FROM ppp_secrets
        WHERE name LIKE ? OR last_caller_id LIKE ?

        UNION ALL

        -- 3. SmartOLT
        SELECT 
            pppoe_username as pppoe,
            'No Vinculado' as nombre,
            'SN: ' || sn as direccion,
            0 as id,
            'smartolt' as origen,
            '' as mac
        FROM subscribers
        WHERE pppoe_username LIKE ? OR sn LIKE ?
        LIMIT 50
        """
        
        # Argumentos: 3 para ISPCube, 2 para Mikrotik, 2 para SmartOLT
        args = (term, term, term, term, term, term, term)
        self.cursor.execute(sql, args)
        rows = self.cursor.fetchall()

        # DEDUPLICACIÓN INTELIGENTE EN PYTHON
        # Si un cliente está en ISPCube y en Mikrotik, el UNION ALL trae los dos.
        # Usamos un diccionario para quedarnos con la "mejor" versión (ISPCube > Mikrotik > SmartOLT).
        results_map = {}
        
        for r in rows:
            pppoe = r['pppoe']
            origen = r['origen']
            
            # Si ya existe y el que tenemos es 'ispcube', no lo pisamos con uno técnico
            if pppoe in results_map:
                if results_map[pppoe]['origen'] == 'ispcube':
                    continue # Ya tenemos la mejor data
                
                # Si el nuevo es ispcube, pisa al viejo
                if origen == 'ispcube':
                    results_map[pppoe] = dict(r)
                
                # Si tenemos uno técnico y viene otro técnico, podemos enriquecer (opcional), 
                # pero por velocidad simplemente dejamos el primero o priorizamos MK sobre OLT
                elif origen == 'mikrotik' and results_map[pppoe]['origen'] == 'smartolt':
                    results_map[pppoe] = dict(r)
            else:
                results_map[pppoe] = dict(r)

        return list(results_map.values())

    # ------------------ DIAGNÓSTICO DIRECTO ------------------
    def get_diagnosis(self, pppoe_user: str) -> dict:
        # 1. Buscar en ISPCube (Query simple y rápida)
        sql_admin = """
        SELECT s.unique_external_id, s.pppoe_username, s.sn AS onu_sn, s.mode as Modo, s.olt_name AS OLT,
                n.name AS nodo_nombre, n.ip_address AS nodo_ip, n.puerto AS puerto, p.name AS plan,
                c.direccion AS direccion, l.name AS cliente_nombre
        FROM connections c
        JOIN clientes l ON c.customer_id = l.id
        LEFT JOIN subscribers s ON c.pppoe_username = s.pppoe_username
        LEFT JOIN nodes n ON c.node_id = n.node_id
        LEFT JOIN plans p ON c.plan_id = p.plan_id
        WHERE c.pppoe_username = ?
        """
        self.cursor.execute(sql_admin, (pppoe_user,))
        row_admin = self.cursor.fetchone()

        # 2. Buscar datos técnicos (Secret) por separado
        self.cursor.execute("SELECT router_ip, last_caller_id, comment FROM ppp_secrets WHERE name = ?", (pppoe_user,))
        secret_row = self.cursor.fetchone()

        diagnosis = {}

        if row_admin:
            diagnosis = dict(row_admin)
            if secret_row:
                diagnosis['mac'] = secret_row['last_caller_id']
                # Corrección de IP: Si Mikrotik dice otra cosa, es la verdad
                real_ip = secret_row['router_ip']
                if real_ip and real_ip != diagnosis['nodo_ip']:
                    self.cursor.execute("SELECT name, puerto FROM nodes WHERE ip_address = ?", (real_ip,))
                    real_node = self.cursor.fetchone()
                    if real_node:
                        diagnosis['nodo_nombre'] = real_node['name']
                        diagnosis['nodo_ip'] = real_ip
                        diagnosis['puerto'] = real_node['puerto']
                    else:
                        diagnosis['nodo_nombre'] = f"Router {real_ip}"
                        diagnosis['nodo_ip'] = real_ip
                        diagnosis['puerto'] = None
            return diagnosis

        # 3. Fallback: No Vinculado
        self.cursor.execute("SELECT * FROM subscribers WHERE pppoe_username = ?", (pppoe_user,))
        sub_row = self.cursor.fetchone()

        if not sub_row and not secret_row:
             return {"error": f"Cliente {pppoe_user} no encontrado."}

        diagnosis = {
            "cliente_nombre": "No Vinculado", "direccion": "N/A", "plan": "N/A", "pppoe_username": pppoe_user,
            "onu_sn": "N/A", "Modo": "N/A", "OLT": "N/A", "nodo_nombre": "Desconocido", "nodo_ip": None,
            "puerto": None, "unique_external_id": None, "mac": None
        }

        if sub_row:
             diagnosis.update({"unique_external_id": sub_row['unique_external_id'], "onu_sn": sub_row['sn'], "OLT": sub_row['olt_name'], "Modo": sub_row['mode']})
        
        if secret_row:
            diagnosis['mac'] = secret_row['last_caller_id']
            if secret_row['comment']: diagnosis['cliente_nombre'] += f" ({secret_row['comment']})"
            
            real_ip = secret_row['router_ip']
            if real_ip:
                self.cursor.execute("SELECT name, ip_address, puerto FROM nodes WHERE ip_address = ?", (real_ip,))
                node_row = self.cursor.fetchone()
                if node_row:
                    diagnosis.update({"nodo_nombre": node_row['name'], "nodo_ip": node_row['ip_address'], "puerto": node_row['puerto']})
                else:
                    diagnosis.update({"nodo_nombre": f"Router {real_ip}", "nodo_ip": real_ip, "puerto": None})

        return diagnosis

    def commit(self): self.conn.commit()
    def close(self): self.conn.close()

# ------------------ INIT DB (Con Índices) ------------------
def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    # Tablas
    cursor.execute("CREATE TABLE IF NOT EXISTS subscribers (unique_external_id TEXT PRIMARY KEY, pppoe_username TEXT, sn TEXT, olt_name TEXT, olt_id TEXT, board TEXT, port TEXT, onu TEXT, onu_type_id TEXT, mode TEXT, node_id TEXT, connection_id TEXT, vlan TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS nodes (node_id TEXT PRIMARY KEY, name TEXT, ip_address TEXT, puerto TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS plans (plan_id TEXT PRIMARY KEY, name TEXT, speed TEXT, description TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS connections (connection_id TEXT PRIMARY KEY, pppoe_username TEXT, customer_id TEXT, node_id TEXT, plan_id TEXT, direccion TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, code TEXT, name TEXT, tax_residence TEXT, type TEXT, tax_situation_id INTEGER, identification_type_id INTEGER, doc_number TEXT, auto_bill_sending INTEGER, auto_payment_recipe_sending INTEGER, nickname TEXT, comercial_activity TEXT, address TEXT, between_address1 TEXT, between_address2 TEXT, city_id INTEGER, lat TEXT, lng TEXT, extra1 TEXT, extra2 TEXT, entity_id INTEGER, collector_id INTEGER, seller_id INTEGER, block INTEGER, free INTEGER, apply_late_payment_due INTEGER, apply_reconnection INTEGER, contract INTEGER, contract_type_id INTEGER, contract_expiration_date TEXT, paycomm TEXT, expiration_type_id INTEGER, business_id INTEGER, first_expiration_date TEXT, second_expiration_date TEXT, next_month_corresponding_date INTEGER, start_date TEXT, perception_id INTEGER, phonekey TEXT, debt TEXT, duedebt TEXT, speed_limited INTEGER, status TEXT, enable_date TEXT, block_date TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT, temporary INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes_emails (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, email TEXT NOT NULL, FOREIGN KEY (customer_id) REFERENCES clientes(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes_telefonos (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, number TEXT NOT NULL, FOREIGN KEY (customer_id) REFERENCES clientes(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS sync_status (id INTEGER PRIMARY KEY AUTOINCREMENT, fuente TEXT NOT NULL, ultima_actualizacion TEXT NOT NULL, estado TEXT NOT NULL, detalle TEXT)")
    
    # Tabla Secrets simple
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

    # ÍNDICES VITALES
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_connections_pppoe ON connections(pppoe_username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_pppoe ON subscribers(pppoe_username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_name ON clientes(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_secrets_lastcaller ON ppp_secrets(last_caller_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_secrets_name ON ppp_secrets(name)")
    
    conn.commit()
    conn.close()