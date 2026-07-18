import os
import shutil
import sqlite3
import tempfile
import unittest

import app as app_module


class UiAndProfileRegressionTests(unittest.TestCase):
    def test_viewport_meta_tag_is_zoom_safe(self):
        app_module.app.config.update(TESTING=True)
        client = app_module.app.test_client()
        response = client.get('/login')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"', html)

    def test_photo_url_supports_uploads_prefix(self):
        url = app_module.photo_url('uploads/avatar.png')
        self.assertEqual(url, '/uploads/avatar.png')

    def test_admin_can_add_bank_when_legacy_schema_is_missing_account_holder_name(self):
        tmp_dir = tempfile.mkdtemp()
        tmp_db_path = os.path.join(tmp_dir, 'altajobs.db')
        try:
            original_db = app_module.DATABASE
            app_module.DATABASE = tmp_db_path
            app_module.init_db()

            with sqlite3.connect(tmp_db_path) as conn:
                conn.execute('ALTER TABLE bank_accounts RENAME TO bank_accounts_old')
                conn.execute('''
                    CREATE TABLE bank_accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bank_name TEXT NOT NULL,
                        account_number TEXT NOT NULL,
                        account_name TEXT DEFAULT NULL,
                        is_active INTEGER DEFAULT 1,
                        created_at TEXT NOT NULL
                    )
                ''')
                conn.commit()

            app_module.app.config.update(TESTING=True)
            client = app_module.app.test_client()
            with client.session_transaction() as session:
                session['user_id'] = 1
                session['lang'] = 'en'

            # Seed an admin user
            with sqlite3.connect(tmp_db_path) as conn:
                conn.execute("DELETE FROM users WHERE id = 1")
                conn.execute("INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (1, 'admin', 'admin@example.com', 'hash', 'Admin', 'worker', '2024-01-01T00:00:00', 1))
                conn.commit()

            with app_module.app.app_context():
                app_module.g._database = None
                app_module.g.pop('_database', None)

            response = client.post('/admin/settings', data={
                'action': 'create_bank',
                'bank_name': 'CBE',
                'account_number': '1234567890',
                'account_holder_name': 'AltaJobs',
                'is_active': '1',
            }, follow_redirects=True)

            self.assertEqual(response.status_code, 200)
            with sqlite3.connect(tmp_db_path) as conn:
                row = conn.execute("SELECT bank_name, account_number FROM bank_accounts WHERE bank_name = ?", ('CBE',)).fetchone()
            self.assertIsNotNone(row)
        finally:
            app_module.DATABASE = original_db
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
