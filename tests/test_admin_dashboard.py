import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module


class AdminDashboardTests(unittest.TestCase):
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

    def test_admin_approval_actions_show_feedback(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        self.db.execute("DELETE FROM users WHERE id = ?", (1,))
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'admin', 'admin@example.com', 'hash', 'Admin', 'worker', '2024-01-01T00:00:00', 0, 1),
        )
        self.db.execute(
            "INSERT INTO wallet_transactions (id, user_id, tx_type, amount, note, status, created_at, bank, transaction_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 1, 'deposit', 50, 'Deposit test', 'pending', '2024-01-01T00:00:00', 'CBE', 'TX-001'),
        )
        self.db.commit()

        response = self.client.post('/admin/approve-deposit/1', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True).lower()
        self.assertIn('deposit request approved', html)


if __name__ == '__main__':
    unittest.main()
