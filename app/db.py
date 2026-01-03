import os
import sqlite3
import pathlib
from dotenv import load_dotenv

load_dotenv()

DB_PATH = pathlib.Path(__file__).resolve().parent / "data" / "counters.sqlite3"
RECEIPT_COUNTER_NAME = "last_receipt_number"
RECEIPT_NUMBER_RESET_AT = int(os.getenv('RECEIPT_NUMBER_RESET_AT', '99'))


def _ensure_db():
    """Create DB file and counters table if missing."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                last INTEGER NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def peek_next_receipt_number(max_val=RECEIPT_NUMBER_RESET_AT):
    """Return next receipt number in range 1..max_val without committing it."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT last FROM counters WHERE name=?", (RECEIPT_COUNTER_NAME,))
        row = cur.fetchone()
        last = int(row[0]) if row and row[0] is not None else 0
        next_num = (last % max_val) + 1
        return next_num
    finally:
        conn.close()


def commit_receipt_number(number):
    """Atomically save provided receipt number as last used."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # Upsert pattern
        cur.execute(
            "INSERT INTO counters(name, last) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET last=excluded.last",
            (RECEIPT_COUNTER_NAME, int(number)),
        )
        conn.commit()
        return True
    except Exception as e:
        print("Failed to commit receipt number:", e)
        return False
    finally:
        conn.close()
