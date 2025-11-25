# app/db/sqlite.py
import sqlite3
from app import config

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
            name TEXT,
            mode TEXT,
            node_id TEXT,
            connection_id TEXT
        )
    """)

    # Tabla de nodos (ISPCube) name = nombre del nodo (comment en ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT,
            ip_address TEXT
        )
    """)

    # Tabla de conexiones (ISPCube)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            connection_id TEXT PRIMARY KEY,
            pppoe_username TEXT,
            customer_id TEXT,
            node_id TEXT
        )
    """)

    conn.commit()
    conn.close()

def insert_subscriber(unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode):
    conn = sqlite3.connect(config.DB_PATH)   # o beholder.db, según uses
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscribers (
            unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode))
    conn.commit()
    conn.close()


def insert_node(node_id, name, ip_address):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO nodes (node_id, name, ip_address)
        VALUES (?, ?, ?)
    """, (node_id, name, ip_address))
    conn.commit()
    conn.close()

def insert_connection(connection_id, pppoe_username, customer_id, node_id):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO connections (connection_id, pppoe_username, customer_id, node_id)
        VALUES (?, ?, ?, ?)
    """, (connection_id, pppoe_username, customer_id, node_id))
    conn.commit()
    conn.close()

def match_connections():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
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
    conn.commit()
    conn.close()



def get_subscriber_by_pppoe(pppoe_user):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscribers WHERE pppoe_user = ?", (pppoe_user,))
    row = cursor.fetchone()
    conn.close()
    return row