# app/db/sqlite.py
import sqlite3
from app import config

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

    def insert_node(self, node_id, name, ip_address):
        self.cursor.execute("""
            INSERT OR REPLACE INTO nodes (node_id, name, ip_address)
            VALUES (?, ?, ?)
        """, (node_id, name, ip_address))

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
    
    def log_sync_status(self, fuente: str, estado: str, detalle: str = None):
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
                s.olt_name AS OLT,
                n.name AS nodo_nombre,
                n.ip_address AS nodo_ip,
                p.name AS plan,
                c.address AS direccion
        FROM subscribers s
        LEFT JOIN connections c ON s.connection_id = c.connection_id
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
            "OLT": row[3],
            "nodo_nombre": row[4],
            "nodo_ip": row[5],
            "plan": row[6],
            "direccion": row[7]
        }
        return diagnosis
    
    def get_diagnosis_base(self, pppoe_user: str) -> dict:
        query = """
        SELECT s.unique_external_id, s.pppoe_username, s.sn, s.olt_name,
               c.connection_id, c.node_id, c.plan_id
        FROM subscribers s
        LEFT JOIN connections c ON s.connection_id = c.connection_id
        WHERE s.pppoe_username = ?
        """
        self.cursor.execute(query, (pppoe_user,))
        row = self.cursor.fetchone()
        if not row:
            return None

        return {
            "unique_external_id": row[0],
            "pppoe_username": row[1],
            "onu_sn": row[2],
            "olt_name": row[3],
            "connection_id": row[4],
            "node_id": row[5],
            "plan_id": row[6]
        }



    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


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
            connection_id TEXT
        )
    """)

    # Tabla de nodos (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT,          -- nombre del nodo (comment en ISPCube)
            ip_address TEXT
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
