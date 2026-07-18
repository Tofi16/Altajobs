import os
import sys
import tempfile
import unittest
from unittest.mock import patch

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
            'bankSelection': 'CBE',
            'bankNameManual': '',
            'accountNumber': '1234567890',
            'accountName': 'Tester User',
            'amount': '25'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        row = db.execute("SELECT * FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' ORDER BY id DESC LIMIT 1", (1,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['amount'], 25)
        self.assertEqual(row['bank'], 'CBE')
        self.assertEqual(row['status'], 'pending')
        self.assertEqual(row['note'], 'Account: Tester User | Account Number: 1234567890')
        self.assertEqual(row['account_number'], '1234567890')
        self.assertEqual(row['account_name'], 'Tester User')

        balance = db.execute("SELECT wallet_balance FROM users WHERE id = ?", (1,)).fetchone()[0]
        self.assertEqual(balance, 100)

    def test_withdrawal_form_submits_with_active_bank_id(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        db = app_module.get_db()
        db.execute("DELETE FROM users WHERE id = ?", (1,))
        db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'tester', 'tester@example.com', 'hash', 'Tester', 'worker', '2024-01-01T00:00:00', 100),
        )
        db.execute(
            "INSERT INTO bank_accounts (bank_name, account_number, account_holder_name, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
            ('CBE', '1234567890', 'Tester User', 1, '2024-01-01T00:00:00'),
        )
        bank_id = db.execute("SELECT id FROM bank_accounts WHERE bank_name = ?", ('CBE',)).fetchone()[0]
        db.commit()

        response = self.client.post('/withdraw', data={
            'bank_id': str(bank_id),
            'amount': '25',
            'accountNumber': '1234567890',
            'accountName': 'Tester User'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        row = db.execute("SELECT * FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' ORDER BY id DESC LIMIT 1", (1,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['bank'], 'CBE')
        self.assertEqual(row['account_number'], '1234567890')
        self.assertEqual(row['account_name'], 'Tester User')

    def test_withdrawal_form_accepts_modal_field_names(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        db = app_module.get_db()
        db.execute("DELETE FROM users WHERE id = ?", (1,))
        db.execute("INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (1, 'tester', 'tester@example.com', 'hash', 'Tester', 'worker', '2024-01-01T00:00:00', 100))
        db.commit()

        response = self.client.post('/withdraw', data={
            'amount': '25',
            'bankSelection': 'CBE',
            'bankNameManual': '',
            'auth_pin': 'secret',
            'accountName': 'Tester User',
            'accountNumber': '1234567890',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        row = db.execute("SELECT * FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' ORDER BY id DESC LIMIT 1", (1,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['amount'], 25)
        self.assertEqual(row['bank'], 'CBE')
        self.assertEqual(row['status'], 'pending')
        self.assertEqual(row['account_number'], '1234567890')
        self.assertEqual(row['account_name'], 'Tester User')

    def test_duplicate_pending_withdrawal_is_blocked(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        db = app_module.get_db()
        db.execute("DELETE FROM users WHERE id = ?", (1,))
        db.execute("INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (1, 'tester', 'tester@example.com', 'hash', 'Tester', 'worker', '2024-01-01T00:00:00', 100))
        db.commit()

        first = self.client.post('/withdraw', data={
            'bankSelection': 'CBE',
            'bankNameManual': '',
            'accountNumber': '1234567890',
            'accountName': 'Tester User',
            'amount': '25'
        }, follow_redirects=True)
        second = self.client.post('/withdraw', data={
            'bankSelection': 'CBE',
            'bankNameManual': '',
            'accountNumber': '1234567890',
            'accountName': 'Tester User',
            'amount': '30'
        }, follow_redirects=True)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        pending_rows = db.execute("SELECT * FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' AND status = 'pending'", (1,)).fetchall()
        self.assertEqual(len(pending_rows), 1)
        self.assertIn('pending withdrawal', second.get_data(as_text=True).lower())

    def test_wallet_page_renders_without_optional_user_columns(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        minimal_user = {
            'id': 1,
            'username': 'tester',
            'is_admin': False,
            'balance': 100,
            'wallet_balance': 100,
            'created_at': '2024-01-01T00:00:00',
            'paid_until': None,
            'is_verified': False,
            'is_vip': False,
        }

        with patch.object(app_module, 'get_current_user', return_value=minimal_user):
            response = self.client.get('/wallet')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Available Balance', html)
        self.assertIn('No Transactions Yet', html)


if __name__ == '__main__':
    unittest.main()
