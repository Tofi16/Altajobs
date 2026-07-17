import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as app_module


def test_schema_and_admin_seed(tmp_path):
    db_path = tmp_path / "schema-test.db"
    app_module.DATABASE = str(db_path)
    app_module.init_db()

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "users" in tables
        assert "wallets" in tables
        assert "products" in tables
        assert "transactions" in tables
        assert "offers" in tables
        assert "announcements" in tables
        assert "restricted_words" in tables

        user = conn.execute(
            "SELECT id, username, role, is_admin FROM users WHERE username = ?",
            ("Tofik",),
        ).fetchone()
        assert user is not None
        assert user[1] == "Tofik"
        assert user[2] == "admin"
        assert user[3] == 1

        wallet = conn.execute("SELECT user_id FROM wallets WHERE user_id = ?", (user[0],)).fetchone()
        assert wallet is not None
