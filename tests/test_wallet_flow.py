import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module


class WalletFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        app_module.DATABASE = self.tmp_db.name
        app_module.init_db()
        app_module.app.config.update(TESTING=True)
        self.app_context = app_module.app.app_context()
        self.app_context.push()
        self.client = app_module.app.test_client()
        self.db = app_module.get_db()

    def tearDown(self):
        self.db.close()
        self.app_context.pop()
        os.unlink(self.tmp_db.name)

    def test_wallet_page_returns_safe_response_if_db_errors(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        self.db.execute("DELETE FROM users WHERE id = ?", (1,))
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'walletuser', 'wallet@example.com', 'hash', 'Wallet User', 'worker', '2024-01-01T00:00:00', 0),
        )
        self.db.commit()

        class FakeCursor:
            def __init__(self, row=None):
                self._row = row
            def fetchone(self):
                return self._row
            def fetchall(self):
                return []

        class FailingDb:
            def execute(self, sql, params=()):
                if 'SELECT is_banned' in sql:
                    return FakeCursor({'is_banned': 0, 'banned_until': None})
                raise RuntimeError('db exploded')
            def commit(self):
                pass
            def rollback(self):
                pass
            def close(self):
                pass
            is_sqlite = True

        app_module.get_db = lambda: FailingDb()
        app_module.get_current_user = lambda: {'id': 1, 'is_admin': False, 'is_banned': 0, 'banned_until': None}

        response = self.client.get('/wallet')

        self.assertIn(response.status_code, (200, 302))


if __name__ == '__main__':
    unittest.main()
