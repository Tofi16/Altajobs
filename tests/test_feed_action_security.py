import os
import tempfile
import unittest

import app as app_module


class FeedActionSecurityTests(unittest.TestCase):
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
                "INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)",
                (1001, 'owner', 'hash', 0, '2025-01-01T00:00:00', 'Owner User'),
            )
            db.execute(
                "INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)",
                (1002, 'other', 'hash', 0, '2025-01-01T00:00:00', 'Other User'),
            )
            db.execute(
                "INSERT INTO posts (id, user_id, content, created_at, status) VALUES (?, ?, ?, ?, ?)",
                (10001, 1001, 'Owned post', '2025-01-01T00:00:00', 'posted'),
            )
            db.commit()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_other_user_cannot_delete_post(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1002

        response = self.client.post('/post/10001/delete', follow_redirects=False)

        self.assertEqual(response.status_code, 403)

    def test_like_route_returns_json_and_persists_state(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1002

        response = self.client.post('/post/10001/like', headers={'X-Requested-With': 'XMLHttpRequest'})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['liked'])
        self.assertEqual(data['like_count'], 1)


if __name__ == '__main__':
    unittest.main()
