import sqlite3
from datetime import datetime
from config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT,
            niche TEXT,
            topic TEXT UNIQUE,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def is_topic_exists(topic: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM content_history WHERE LOWER(topic) = LOWER(?)", (topic.strip(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def save_topic(content_type: str, niche: str, topic: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO content_history (content_type, niche, topic, created_at) VALUES (?, ?, ?, ?)",
            (content_type, niche, topic.strip(), datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def get_recent_topics(niche: str, limit: int = 15) -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT topic FROM content_history WHERE LOWER(niche) = LOWER(?) ORDER BY id DESC LIMIT ?",
        (niche.strip(), limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

init_db()