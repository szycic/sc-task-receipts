"""Database module for SC Task Receipts.

Handles SQLite connection and atomic updates for tracking receipt numbers
to prevent duplicate printing numbers.
"""

import os
import pathlib
import sqlite3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Locate the root of the project to configure default paths
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Determine the SQLite database location
_env_db = os.getenv('DB_PATH')
if _env_db:
    DB_PATH = pathlib.Path(_env_db).expanduser()
else:
    DB_PATH = PROJECT_ROOT / "data" / "counters.sqlite3"

# Key name used in the counters table for tracking receipt numbering
RECEIPT_COUNTER_NAME = "last_receipt_number"

# Threshold at which receipt numbering rolls back to 1
RECEIPT_NUMBER_RESET_AT = int(os.getenv('RECEIPT_NUMBER_RESET_AT', '99'))


def _ensure_db() -> None:
    """Create the SQLite database file and counters table if they do not exist.

    Ensures that the directory structure exists before opening the database connection.
    """
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


def peek_next_receipt_number(max_val: int = RECEIPT_NUMBER_RESET_AT) -> int:
    """Retrieve the next sequential receipt number without saving or committing it.

    Args:
        max_val: The maximum value after which the receipt number resets back to 1.

    Returns:
        The next receipt number (integer) in the range [1, max_val].
    """
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


def commit_receipt_number(number: int) -> bool:
    """Atomically commit a receipt number to the database as the last used number.

    Args:
        number: The receipt number to persist.

    Returns:
        True if the number was saved successfully, False otherwise.
    """
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # Upsert pattern to insert or update the existing counter
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

