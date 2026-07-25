import os
import tempfile
import app as app_module

app_module.app.config['TESTING'] = True
fd, path = tempfile.mkstemp(suffix='.db')
os.close(fd)
app_module.DATABASE = path
app_module.DATABASE_URL = 'sqlite:///' + path.replace('\\', '/')
app_module.USE_SQLITE = True
app_module.init_db()
client = app_module.app.test_client()
with app_module.app.app_context():
    db = app_module.get_db()
    db.execute("INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)", (1001, 'owner', 'hash', 0, '2025-01-01T00:00:00', 'Owner User'))
    db.execute("INSERT INTO users (id, username, password_hash, is_admin, created_at, full_name) VALUES (?, ?, ?, ?, ?, ?)", (1002, 'other', 'hash', 0, '2025-01-01T00:00:00', 'Other User'))
    db.execute("INSERT INTO posts (id, user_id, content, created_at, status) VALUES (?, ?, ?, ?, ?)", (10001, 1001, 'Owned post', '2025-01-01T00:00:00', 'posted'))
    db.commit()

with client.session_transaction() as session:
    session['user_id'] = 1002
resp = client.post('/post/10001/like', headers={'X-Requested-With': 'XMLHttpRequest'})
print('status', resp.status_code)
print(resp.get_data(as_text=True))
print(resp.get_json())
