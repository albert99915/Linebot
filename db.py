import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "reservations.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            people INTEGER NOT NULL,
            service TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def add_reservation(user_id, name, date, time, people, service):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reservations (user_id, name, date, time, people, service) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, date, time, people, service),
    )
    reservation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return reservation_id


def get_user_reservations(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reservations WHERE user_id = ? ORDER BY date, time",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def delete_reservation(reservation_id, user_id):
    conn = get_connection()
    affected = conn.execute(
        "DELETE FROM reservations WHERE id = ? AND user_id = ?",
        (reservation_id, user_id),
    ).rowcount
    conn.commit()
    conn.close()
    return affected > 0
