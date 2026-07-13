import csv
import sqlite3
from datetime import datetime, timezone

DB_PATH = "data/flyiop.db"


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            flight_date TEXT,
            price REAL NOT NULL,
            currency TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def insert_price(conn: sqlite3.Connection, route_id: str, flight_date: str, price: float, currency: str) -> None:
    conn.execute(
        "INSERT INTO price_history (route_id, checked_at, flight_date, price, currency) VALUES (?, ?, ?, ?, ?)",
        (route_id, datetime.now(timezone.utc).isoformat(), flight_date, price, currency),
    )
    conn.commit()


def get_recent_prices(conn: sqlite3.Connection, route_id: str, days: int) -> list[tuple[str, float]]:
    cursor = conn.execute(
        """
        SELECT checked_at, price FROM price_history
        WHERE route_id = ? AND checked_at >= datetime('now', ?)
        ORDER BY checked_at ASC
        """,
        (route_id, f"-{days} days"),
    )
    return cursor.fetchall()


def get_all_prices(conn: sqlite3.Connection, route_id: str) -> list[tuple[str, float]]:
    cursor = conn.execute(
        "SELECT checked_at, price FROM price_history WHERE route_id = ? ORDER BY checked_at ASC",
        (route_id,),
    )
    return cursor.fetchall()


def export_csv(conn: sqlite3.Connection, path: str = "data/flyiop_history.csv") -> None:
    cursor = conn.execute(
        "SELECT route_id, checked_at, flight_date, price, currency FROM price_history ORDER BY checked_at ASC"
    )
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["route_id", "checked_at", "flight_date", "price", "currency"])
        writer.writerows(cursor.fetchall())
