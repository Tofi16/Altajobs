import datetime
import os
import shutil
import sqlite3
import tempfile
import unittest

import app as app_module


class LanguageAndVerificationTests(unittest.TestCase):
    def test_default_language_is_english_and_verification_columns_exist(self):
        self.assertEqual(app_module.DEFAULT_LANG, "en")

        tmp_dir = tempfile.mkdtemp()
        tmp_db_path = os.path.join(tmp_dir, "altajobs.db")
        try:
            original_db = app_module.DATABASE
            app_module.DATABASE = tmp_db_path
            app_module.init_db()
            with sqlite3.connect(tmp_db_path) as conn:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            self.assertIn("email_verified", cols)
            self.assertIn("email_verification_code", cols)
        finally:
            app_module.DATABASE = original_db
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_legacy_verification_flags_fall_back_to_effective_tier(self):
        self.assertEqual(app_module.get_verification_tier({
            "is_verified": True,
            "verified_until": (datetime.datetime.utcnow() + datetime.timedelta(days=5)).isoformat(),
        }), "blue")
        self.assertEqual(app_module.get_verification_tier({
            "is_vip": True,
            "verified_until": (datetime.datetime.utcnow() + datetime.timedelta(days=5)).isoformat(),
        }), "gold")
        self.assertEqual(app_module.get_verification_tier({
            "is_vip": True,
            "verified_until": (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat(),
        }), "none")

    def test_buying_blue_does_not_downgrade_existing_gold(self):
        # Set up a temp db with a gold user and enough wallet balance.
        tmp_dir = tempfile.mkdtemp()
        tmp_db_path = os.path.join(tmp_dir, "altajobs.db")
        original_db = app_module.DATABASE
        app_module.DATABASE = tmp_db_path
        app_module.app.config.update(TESTING=True)
        client = app_module.app.test_client()
        try:
            app_module.init_db()
            with sqlite3.connect(tmp_db_path) as conn:
                conn.execute("INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, verification_tier, verified_until, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (2, 'golduser', 'gold@example.com', 'hash', 'Gold User', 'worker', datetime.datetime.utcnow().isoformat(), 'gold', (datetime.datetime.utcnow() + datetime.timedelta(days=10)).isoformat(), 1000.0))
                conn.commit()

            with app_module.app.app_context():
                app_module.g._database = None
                app_module.g.pop('_database', None)

            with client.session_transaction() as session:
                session['user_id'] = 2
                session['lang'] = 'en'

            response = client.post('/verify/buy', follow_redirects=True)
            self.assertEqual(response.status_code, 200)

            with sqlite3.connect(tmp_db_path) as conn:
                row = conn.execute("SELECT verification_tier, verified_until FROM users WHERE id = 2").fetchone()
            self.assertEqual(row[0], 'gold')
        finally:
            app_module.DATABASE = original_db
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
