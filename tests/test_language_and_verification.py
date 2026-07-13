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


if __name__ == "__main__":
    unittest.main()
