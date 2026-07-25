import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.test_feed_action_security import FeedActionSecurityTests

suite = unittest.defaultTestLoader.loadTestsFromTestCase(FeedActionSecurityTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
