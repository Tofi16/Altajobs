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

    def test_deposit_form_submits_with_legacy_wallet_schema(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        self.db.execute("DELETE FROM users WHERE id = ?", (1,))
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'walletuser', 'wallet@example.com', 'hash', 'Wallet User', 'worker', '2024-01-01T00:00:00', 0),
        )
        self.db.execute("DELETE FROM bank_accounts")
        self.db.execute(
            "INSERT INTO bank_accounts (id, bank_name, account_number, account_holder_name, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, 'CBE', '1000001', 'Wallet User', 1, '2024-01-01T00:00:00'),
        )
        self.db.commit()

        response = self.client.post('/wallet/deposit', data={
            'amount': '250',
            'bank_id': '1',
            'transaction_ref': 'DEP-001',
            'note': 'Deposit test',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        row = self.db.execute("SELECT * FROM wallet_transactions WHERE tx_type = 'deposit' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['amount'], 250)
        self.assertEqual(row['transaction_ref'], 'DEP-001')
        self.assertEqual(row['bank'], 'CBE')

    def test_missing_wallet_id_is_backfilled_for_existing_user(self):
        self.db.execute("DELETE FROM users WHERE username = ?", ('Tofik',))
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (999, 'Tofik', 'tofik@example.com', 'hash', 'Tofik', 'worker', '2024-01-01T00:00:00'),
        )
        self.db.commit()

        app_module._backfill_missing_wallet_ids(self.db)

        row = self.db.execute("SELECT wallet_id FROM users WHERE username = ?", ('Tofik',)).fetchone()
        self.assertTrue(row and row['wallet_id'])
        self.assertTrue(row['wallet_id'].startswith('WAL'))

    def test_send_funds_works_with_sqlite_row_recipient(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        self.db.execute("DELETE FROM users WHERE id IN (?, ?)", (1, 2))
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'sender', 'sender@example.com', 'hash', 'Sender', 'worker', '2024-01-01T00:00:00', 100),
        )
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (2, 'recipient', 'recipient@example.com', 'hash', 'Recipient', 'worker', '2024-01-01T00:00:00', 0),
        )
        self.db.commit()

        response = self.client.post('/wallet/transfer', data={
            'amount': '20',
            'recipient_identifier': 'recipient',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        sender_row = self.db.execute("SELECT balance, wallet_balance FROM users WHERE id = ?", (1,)).fetchone()
        recipient_row = self.db.execute("SELECT balance, wallet_balance FROM users WHERE id = ?", (2,)).fetchone()
        self.assertEqual(sender_row['balance'], 80)
        self.assertEqual(sender_row['wallet_balance'], 80)
        self.assertEqual(recipient_row['balance'], 20)
        self.assertEqual(recipient_row['wallet_balance'], 20)

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
