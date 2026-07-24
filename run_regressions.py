import subprocess, sys, os
root = r'c:\Users\medina\Desktop\altajobs'
cmd = [r'c:\Users\medina\Desktop\altajobs\.venv\Scripts\python.exe', '-m', 'pytest', '-q', 'tests/test_wallet_flow.py', 'tests/test_admin_dashboard.py', 'tests/test_marketplace_flow.py', 'tests/test_ui_and_profile_regressions.py']
print('Running:', ' '.join(cmd))
subprocess.check_call(cmd, cwd=root)
