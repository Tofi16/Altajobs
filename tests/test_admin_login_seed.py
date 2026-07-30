import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as app_module


def test_seeded_admin_login_uses_valid_password_hash(tmp_path):
    db_path = tmp_path / "auth-seed.db"
    app_module.DATABASE = str(db_path)
    app_module.init_db()

    with sqlite3.connect(db_path) as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE username = ?", ("Tofik",)).fetchone()

    assert user is not None
    assert user[0]
    assert app_module.check_password_hash(user[0], "Tofik123!")
