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

        response = self.client.post('/marketplace', data={
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

    def test_admin_can_delete_marketplace_order(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        with app_module.app.app_context():
            db = app_module.get_db()
            db.execute("DELETE FROM users WHERE id IN (?, ?, ?)", (1, 2, 3))
            db.execute(
                "INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)",
                (1, 'admin', 'hash', 1, '2025-01-01T00:00:00', 'Admin User'),
            )
            db.execute(
                "INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)",
                (2, 'seller', 'hash', 0, '2025-01-01T00:00:00', 'Seller User'),
            )
            db.execute(
                "INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)",
                (3, 'buyer', 'hash', 0, '2025-01-01T00:00:00', 'Buyer User'),
            )
            db.execute(
                "INSERT INTO products (id, user_id, title, description, price, location, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (10, 2, 'Phone', 'Used phone', 1200, 'Addis', 'approved', '2025-01-01T00:00:00'),
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS offers (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, buyer_id INTEGER NOT NULL, seller_id INTEGER NOT NULL, offered_price REAL NOT NULL, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL)"
            )
            db.execute(
                "INSERT INTO offers (id, product_id, buyer_id, seller_id, offered_price, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (20, 10, 3, 2, 1200, 'pending', '2025-01-01T00:00:00'),
            )
            db.commit()

        response = self.client.post('/admin/orders/delete/20', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        with app_module.app.app_context():
            db = app_module.get_db()
            row = db.execute("SELECT id FROM offers WHERE id = ?", (20,)).fetchone()
            self.assertIsNone(row)


if __name__ == '__main__':
    unittest.main()
