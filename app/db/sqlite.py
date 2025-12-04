# app/db/sqlite.py
import sqlite3
from app import config
from datetime import datetime


class Database:
    def __init__(self, path=config.DB_PATH):
        self.conn = sqlite3.connect(path)
        self.cursor = self.conn.cursor()

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
        self.cursor.execute("""
            INSERT INTO clientes_emails (customer_id, email)
            VALUES (?, ?)
        """, (customer_id, email))
    
    def insert_cliente_telefono(self, customer_id: int, number: str):
        self.cursor.execute("""
            INSERT INTO clientes_telefonos (customer_id, number)
            VALUES (?, ?)
        """, (customer_id, number))
    
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
    
    def log_sync_status(self, fuente: str, estado: str, detalle: str = ""):
        """Registra el estado de sincronización de una fuente"""
        self.cursor.execute("""
            INSERT INTO sync_status (fuente, ultima_actualizacion, estado, detalle)
            VALUES (?, ?, ?, ?)
        """, (fuente, datetime.now(), estado, detalle))
        self.commit()

    def get_diagnosis(self, pppoe_user: str) -> dict:
        query = """
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
        WHERE s.pppoe_username = ?
        """
        self.cursor.execute(query, (pppoe_user,))
        row = self.cursor.fetchone()

        if not row:
            return {"error": f"Cliente {pppoe_user} no encontrado"}

        diagnosis = {
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
        return diagnosis
    
    

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

### Fin de la clase Database ###
def columnas_tabla(conn, tabla: str) -> set:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({tabla})")
        return {row[1] for row in cur.fetchall()}  # row[1] = nombre columna

def insert_cliente_safe(db, json_cliente: dict):
    cols = columnas_tabla(db.conn, "clientes")
    data = mapear_cliente(json_cliente)

    # Filtrar a solo columnas válidas
    data_filtrada = {k: v for k, v in data.items() if k in cols}

    # Reusar tu método dinámico
    db.insert_cliente(data_filtrada)


# Inicialización de la base de datos y creación de tablas
def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    # Tabla de suscriptores (SmartOLT)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            unique_external_id TEXT PRIMARY KEY,
            pppoe_username TEXT,
            sn TEXT,
            olt_name TEXT,
            olt_id TEXT,
            board TEXT,
            port TEXT,
            onu TEXT,
            onu_type_id TEXT,
            mode TEXT,
            node_id TEXT,
            connection_id TEXT,
            vlan TEXT
        )
    """)

    # Tabla de nodos (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT,          -- nombre del nodo (comment en ISPCube)
            ip_address TEXT,
            puerto TEXT
        )
    """)

    # Tabla de planes (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            plan_id TEXT PRIMARY KEY,
            name TEXT,
            speed TEXT,
            description TEXT
        )
    """)

    # Tabla de conexiones (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            connection_id TEXT PRIMARY KEY,
            pppoe_username TEXT,
            customer_id TEXT,
            node_id TEXT,
            plan_id TEXT,
            direccion TEXT
        )
    """)
    
     # Tabla de clientes (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY,              -- id del cliente
            code TEXT,
            name TEXT,
            tax_residence TEXT,
            type TEXT,
            tax_situation_id INTEGER,
            identification_type_id INTEGER,
            doc_number TEXT,
            auto_bill_sending INTEGER,
            auto_payment_recipe_sending INTEGER,
            nickname TEXT,
            comercial_activity TEXT,
            address TEXT,
            between_address1 TEXT,
            between_address2 TEXT,
            city_id INTEGER,
            lat TEXT,
            lng TEXT,
            extra1 TEXT,
            extra2 TEXT,
            entity_id INTEGER,
            collector_id INTEGER,
            seller_id INTEGER,
            block INTEGER,
            free INTEGER,
            apply_late_payment_due INTEGER,
            apply_reconnection INTEGER,
            contract INTEGER,
            contract_type_id INTEGER,
            contract_expiration_date TEXT,
            paycomm TEXT,
            expiration_type_id INTEGER,
            business_id INTEGER,
            first_expiration_date TEXT,
            second_expiration_date TEXT,
            next_month_corresponding_date INTEGER,
            start_date TEXT,
            perception_id INTEGER,
            phonekey TEXT,
            debt TEXT,
            duedebt TEXT,
            speed_limited INTEGER,
            status TEXT,
            enable_date TEXT,
            block_date TEXT,
            created_at TEXT,
            updated_at TEXT,
            deleted_at TEXT,
            temporary INTEGER
        )

    """)

    #Tabla de emails de clientes (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES clientes(id)
        )
    """)

    #Tabla de teléfonos de clientes (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes_telefonos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            number TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES clientes(id)
        )
    """)

    # Tabla de estados de sincronización
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuente TEXT NOT NULL,                 -- 'smartolt', 'ispcube', 'mikrotik', etc.
            ultima_actualizacion TEXT NOT NULL,   -- ISO 8601 (ej. '2025-11-26T19:45:00')
            estado TEXT NOT NULL,                 -- 'ok', 'empty', 'error'
            detalle TEXT
        )
    """)

    # Índice útil para consultas por fuente y fecha
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_sync_status_fuente_fecha
    ON sync_status (fuente, ultima_actualizacion)
    """)


    conn.commit()
    conn.close()
