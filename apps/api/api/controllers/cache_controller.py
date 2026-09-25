import os
import pickle
import sqlite3
from typing import Any

from rdkit import logger

CACHE_VERSION = "v7"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache", CACHE_VERSION)
CACHE_DB_PATH = os.path.join(CACHE_DIR, "cache.db")
os.makedirs(CACHE_DIR, exist_ok=True)
def init_cache_db():
    """Initialize the SQLite cache database."""
    conn = sqlite3.connect(CACHE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    
def _serialize_value(value: Any) -> bytes:
    """Serialize a value to bytes using pickle."""
    return pickle.dumps(value)

def _deserialize_value(data: bytes) -> Any:
    """Deserialize bytes back to the original value using pickle."""
    return pickle.loads(data)

def cache_get(key: str) -> Any:
    """Get a value from the SQLite cache."""
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM cache WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return _deserialize_value(result[0])
        return None
    except Exception as e:
        logger.warning(f"Cache get error for key '{key}': {e}")
        return None

def cache_set(key: str, value: Any) -> None:
    """Set a value in the SQLite cache."""
    try:
        init_cache_db()  # Ensure DB exists
        serialized_value = _serialize_value(value)
        
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO cache (key, value) 
            VALUES (?, ?)
        ''', (key, serialized_value))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Cache set error for key '{key}': {e}")

