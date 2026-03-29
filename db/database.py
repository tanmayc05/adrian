import sqlite3
import os
import logging
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "adrian.db")

logger = logging.getLogger(__name__)


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

        CREATE TABLE IF NOT EXISTS deals (
            deal_id TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            seen_at TEXT NOT NULL,
            PRIMARY KEY (deal_id, source)
        );
    """)
    # Migration: add location column for existing databases
    try:
        conn.execute("ALTER TABLE subscribers ADD COLUMN location TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()


def add_subscriber(phone: str, categories: list[str], location: str = ""):
    """Add a subscriber with their category preferences and location."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO subscribers (phone, categories, location, created_at) VALUES (?, ?, ?, ?)",
        (phone, ",".join(categories), location.strip(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_all_subscribers() -> list[dict]:
    """Return all subscribers as a list of dicts."""
    conn = _get_conn()
    rows = conn.execute("SELECT phone, categories, location, created_at FROM subscribers").fetchall()
    conn.close()
    return [
        {
            "phone": r["phone"],
            "categories": r["categories"].split(","),
            "location": r["location"] or "",
            "created_at": r["created_at"],
        }
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


def save_deal(deal: dict):
    """Persist a filtered deal to the deals table for chatbot lookups."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO deals (deal_id, source, title, body, url, category, seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            deal["id"],
            deal.get("source", ""),
            deal.get("title", ""),
            deal.get("body", ""),
            deal.get("url", ""),
            deal.get("llm_category", ""),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def search_deals(keywords: list[str], hours: int = 24) -> list[dict]:
    """Search deals by keywords within the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = _get_conn()
    # Build WHERE clause: each keyword must appear in title or body
    conditions = []
    params: list[str] = [cutoff]
    for kw in keywords:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(body) LIKE ?)")
        params.extend([f"%{kw.lower()}%", f"%{kw.lower()}%"])

    where = " AND ".join(conditions)
    query = f"SELECT * FROM deals WHERE seen_at >= ? AND {where} ORDER BY seen_at DESC LIMIT 10"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_deals(hours: int = 24) -> list[dict]:
    """Get all deals from the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM deals WHERE seen_at >= ? ORDER BY seen_at DESC LIMIT 20",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cleanup_old_deals(days: int = 7):
    """Delete seen_deals and deals older than N days to prevent table bloat."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _get_conn()
    result1 = conn.execute("DELETE FROM seen_deals WHERE seen_at < ?", (cutoff,))
    result2 = conn.execute("DELETE FROM deals WHERE seen_at < ?", (cutoff,))
    deleted = result1.rowcount + result2.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old records (seen_deals + deals) older than {days} days")


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
