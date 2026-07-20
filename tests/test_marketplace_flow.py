import os
import sqlite3
import tempfile
import unittest

import app as app_module


class MarketplaceFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        app_module.app.config['TESTING'] = True
        app_module.DATABASE = self.temp_db.name
        app_module.DATABASE_URL = 'sqlite:///' + self.temp_db.name.replace('\\', '/')
        app_module.USE_SQLITE = True
        app_module.init_db()
        self.client = app_module.app.test_client()

        with app_module.app.app_context():
            db = app_module.get_db()
            db.execute(
                "INSERT INTO users (username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, 0, ?, ?)",
                ('seller1', 'hash', '2025-01-01T00:00:00', 'Seller One'),
            )
            db.commit()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_marketplace_listing_is_created_from_form(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

            'title': 'Reliable Laptop',
            'description': 'Used laptop in great shape',
            'price': '2500',
            'location': 'Addis Ababa',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(self.temp_db.name)
        row = conn.execute("SELECT title, status FROM products WHERE title = ?", ('Reliable Laptop',)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'pending')


if __name__ == '__main__':
    unittest.main()
