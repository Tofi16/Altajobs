@echo off
cd /d c:\Users\medina\Desktop\altajobs
set PYTHONPATH=.
"c:/Users/medina/Desktop/altajobs/.venv/Scripts/python.exe" -m unittest -v tests.test_feed_action_security
