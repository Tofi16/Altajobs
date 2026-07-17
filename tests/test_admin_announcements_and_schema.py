import os
import sqlite3
import tempfile
import unittest

import app as app_module


class AdminAnnouncementsAndSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        app_module.app.config['TESTING'] = True
        app_module.app.config['DATABASE'] = self.temp_db.name
        app_module.init_db()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_schema_creates_announcement_tables(self):
        conn = sqlite3.connect(self.temp_db.name)
        cur = conn.cursor()
        for table in ['announcements', 'announcement_views', 'restricted_words']:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            self.assertTrue(cur.fetchone())
        conn.close()

    def test_admin_announcements_route_requires_login(self):
        client = app_module.app.test_client()
        response = client.get('/admin/announcements')
        self.assertIn(response.status_code, (302, 401))


if __name__ == '__main__':
    unittest.main()
