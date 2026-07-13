import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module


class WithdrawalFlowTests(unittest.TestCase):
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

    def test_withdrawal_form_submits_and_is_logged(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        db = app_module.get_db()
        db.execute("DELETE FROM users WHERE id = ?", (1,))
        db.execute("INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (1, 'tester', 'tester@example.com', 'hash', 'Tester', 'worker', '2024-01-01T00:00:00', 100))
        db.commit()

        response = self.client.post('/withdraw', data={
            'bankName': 'CBE',
            'accountNumber': '1234567890',
            'accountName': 'Tester User',
            'amount': '25'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        row = db.execute("SELECT * FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' ORDER BY id DESC LIMIT 1", (1,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['amount'], 25)
        self.assertEqual(row['bank'], 'CBE')
        self.assertEqual(row['note'], 'Account: Tester User | Account Number: 1234567890')
        self.assertEqual(row['account_number'], '1234567890')
        self.assertEqual(row['account_name'], 'Tester User')

        balance = db.execute("SELECT wallet_balance FROM users WHERE id = ?", (1,)).fetchone()[0]
        self.assertEqual(balance, 75)


if __name__ == '__main__':
    unittest.main()
