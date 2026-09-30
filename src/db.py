import sqlite3
import json
import os
from pathlib import Path
from src.config import DATABASE_PATH

DATA_DIR = Path(__file__).parent.parent / "dados"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_db_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessoes (
                session_id TEXT PRIMARY KEY,
                apartamento TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessoes(session_id)
            );

            CREATE TABLE IF NOT EXISTS confirmacoes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                acao TEXT NOT NULL,
                detalhes TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessoes(session_id)
            );

            CREATE TABLE IF NOT EXISTS reservas (
                codigo TEXT PRIMARY KEY,
                apartamento TEXT NOT NULL,
                area TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(area, data)
            );

            CREATE TABLE IF NOT EXISTS visitantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartamento TEXT NOT NULL,
                nome TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.close()

def restore_initial_data():
    init_db()
    conn = get_db_connection()
    with conn:
        # Clear existing non-session tables
        conn.execute("DELETE FROM reservas;")
        conn.execute("DELETE FROM visitantes;")

        # Load initial reservas
        reservas_file = DATA_DIR / "reservas.json"
        if reservas_file.exists():
            with open(reservas_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for r in data:
                    conn.execute(
                        "INSERT OR REPLACE INTO reservas (codigo, apartamento, area, data) VALUES (?, ?, ?, ?)",
                        (r["codigo"], r["apartamento"], r["area"], r["data"])
                    )

        # Load initial visitantes
        visitantes_file = DATA_DIR / "visitantes.json"
        if visitantes_file.exists():
            with open(visitantes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for v in data:
                    conn.execute(
                        "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
                        (v["apartamento"], v["nome"], v["data"])
                    )
    conn.close()

if __name__ == "__main__":
    restore_initial_data()
    print("Database initialized and initial data restored.")
