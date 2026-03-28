import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "reservations.db")

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 22


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
            service TEXT NOT NULL DEFAULT '汗蒸',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('max_capacity', '6')"
    )
    # 遷移：舊資料表可能沒有 status 欄位
    try:
        conn.execute("ALTER TABLE reservations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    except sqlite3.OperationalError:
        pass  # 欄位已存在
    conn.commit()
    conn.close()


def add_reservation(user_id, name, date, time, people, service="汗蒸"):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reservations (user_id, name, date, time, people, service, status) VALUES (?, ?, ?, ?, ?, ?, 'active')",
        (user_id, name, date, time, people, service),
    )
    reservation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return reservation_id


def get_user_reservations(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reservations WHERE user_id = ? AND status = 'active' ORDER BY date, time",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def delete_reservation(reservation_id, user_id):
    conn = get_connection()
    affected = conn.execute(
        "UPDATE reservations SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status = 'active'",
        (reservation_id, user_id),
    ).rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_slot_capacity(date, time):
    """查詢某時段已訂人數"""
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(people), 0) as total FROM reservations WHERE date = ? AND time = ? AND status = 'active'",
        (date, time),
    ).fetchone()
    conn.close()
    return row["total"]


def get_max_capacity():
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'max_capacity'"
    ).fetchone()
    conn.close()
    return int(row["value"]) if row else 6


def set_max_capacity(value):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('max_capacity', ?)",
        (str(value),),
    )
    conn.commit()
    conn.close()


def get_available_hours(date, people):
    """回傳該日有足夠空位的整點時段"""
    max_cap = get_max_capacity()
    available = []
    for h in range(BUSINESS_START_HOUR, BUSINESS_END_HOUR + 1):
        time_str = f"{h:02d}:00"
        booked = get_slot_capacity(date, time_str)
        if booked + people <= max_cap:
            available.append(time_str)
    return available


def get_all_reservations_by_date(date):
    """業主查詢：取得某日所有有效預約"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reservations WHERE date = ? AND status = 'active' ORDER BY time, id",
        (date,),
    ).fetchall()
    conn.close()
    return rows


def cancel_reservation_admin(reservation_id):
    """業主取消預約（不檢查 user_id）"""
    conn = get_connection()
    affected = conn.execute(
        "UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'active'",
        (reservation_id,),
    ).rowcount
    conn.commit()
    conn.close()
    return affected > 0
