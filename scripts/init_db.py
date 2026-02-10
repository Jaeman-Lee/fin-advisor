#!/usr/bin/env python3
"""Initialize the investment advisory database."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.schema import init_db, DB_PATH


def main():
    print(f"Initializing database at: {DB_PATH}")
    path = init_db()
    print(f"Database created successfully: {path}")
    print(f"File size: {path.stat().st_size} bytes")

    # Verify tables
    import sqlite3
    conn = sqlite3.connect(str(path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"\nTables created ({len(tables)}):")
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
        print(f"  - {t[0]} ({count} rows)")
    conn.close()


if __name__ == "__main__":
    main()
