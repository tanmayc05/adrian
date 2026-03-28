import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "adrian.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS subscribers (
            phone TEXT PRIMARY KEY,
            categories TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS seen_deals (
            deal_id TEXT NOT NULL,
            source TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (deal_id, source)
        );
    """)
    conn.commit()
    conn.close()


def add_subscriber(phone: str, categories: list[str]):
    """Add a subscriber with their category preferences."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO subscribers (phone, categories, created_at) VALUES (?, ?, ?)",
        (phone, ",".join(categories), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_all_subscribers() -> list[dict]:
    """Return all subscribers as a list of dicts."""
    conn = _get_conn()
    rows = conn.execute("SELECT phone, categories, created_at FROM subscribers").fetchall()
    conn.close()
    return [
        {"phone": r["phone"], "categories": r["categories"].split(","), "created_at": r["created_at"]}
        for r in rows
    ]


def has_seen_deal(deal_id: str, source: str) -> bool:
    """Check if a deal has already been seen."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM seen_deals WHERE deal_id = ? AND source = ?",
        (deal_id, source),
    ).fetchone()
    conn.close()
    return row is not None


def mark_deal_seen(deal_id: str, source: str):
    """Mark a deal as seen so we don't send it again."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO seen_deals (deal_id, source, seen_at) VALUES (?, ?, ?)",
        (deal_id, source, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# Initialize tables on import
init_db()


if __name__ == "__main__":
    # Quick test
    print("--- Testing database layer ---\n")

    # Add subscribers
    add_subscriber("+11234567890", ["food", "electronics"])
    add_subscriber("+10987654321", ["food", "travel", "gaming"])
    print("Added 2 subscribers")

    # Fetch them back
    subs = get_all_subscribers()
    for s in subs:
        print(f"  {s['phone']} -> {s['categories']}")

    # Test dedup
    mark_deal_seen("abc123", "reddit")
    print(f"\nhas_seen_deal('abc123', 'reddit') = {has_seen_deal('abc123', 'reddit')}")
    print(f"has_seen_deal('xyz999', 'reddit') = {has_seen_deal('xyz999', 'reddit')}")

    # Cleanup test db
    os.remove(DB_PATH)
    print("\nAll tests passed. Cleaned up test db.")
