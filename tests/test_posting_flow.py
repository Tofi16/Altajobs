import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module


class PostingFlowTests(unittest.TestCase):
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

    def test_new_post_succeeds_when_posts_table_is_missing_optional_columns(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1

        self.db.execute("DELETE FROM users WHERE id = ?", (1,))
        self.db.execute(
            "INSERT INTO users (id, username, email, password_hash, full_name, user_type, created_at, wallet_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'poster', 'poster@example.com', 'hash', 'Poster', 'worker', '2024-01-01T00:00:00', 0),
        )
        self.db.commit()

        response = self.client.post('/post/new', data={'content': 'hello from test'}, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        row = self.db.execute("SELECT * FROM posts WHERE user_id = ? ORDER BY id DESC LIMIT 1", (1,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['content'], 'hello from test')


if __name__ == '__main__':
    unittest.main()
