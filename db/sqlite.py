import sqlite3
from app import config

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            pppoe_user TEXT PRIMARY KEY,
            external_id TEXT,
            onu_id TEXT,
            node_code TEXT,
            vlan_info TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def insert_subscriber(unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode):
    conn = sqlite3.connect("diag.db")   # o beholder.db, según uses
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscribers (
            unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (unique_external_id, sn, olt_name, olt_id, board, port, onu, onu_type_id, name, mode))
    conn.commit()
    conn.close()

def get_subscriber_by_pppoe(pppoe_user):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscribers WHERE pppoe_user = ?", (pppoe_user,))
    row = cursor.fetchone()
    conn.close()
    return row