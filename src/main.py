from flask import Flask, jsonify, request, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
import jwt

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///altajobs.db'
db = SQLAlchemy(app)

# Define User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

# Define Feed model
class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)

@app.before_request
def check_auth():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'message': 'Authentication required'}), 401
    
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'])
        current_user = User.query.filter_by(id=payload['id']).first()
        if not current_user:
            return jsonify({'message': 'Invalid token'}), 401
    except Exception as e:
        return jsonify({'message': 'Failed to authenticate'}), 401

@app.route('/feeds', methods=['GET'])
@login_required
def fetch_feeds():
    user_id = current_user.id
    
    # Fetch all public feeds or feeds belonging to the current logged-in user
    if not request.args.get('public'):
        feeds = Feed.query.filter_by(user=user_id).all()
    else:
        feeds = Feed.query.all()
    
    # Prepare a list to hold the formatted feed data
    formatted_feeds = []
    for feed in feeds:
        # Exclude sensitive user data from the response
        formatted_feed = {
            'id': feed.id,
            'title': feed.title,
            'content': feed.content,
            'author_name': feed.author.name,
        }
        formatted_feeds.append(formatted_feed)
    
    return jsonify(formatted_feeds)

# Example user class
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

# Example feed class
class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)

# Example login route (for demonstration purposes, you should use a real authentication mechanism)
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    token = jwt.encode({'id': user.id}, app.config['SECRET_KEY'])
    return jsonify({'token': token}), 200

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)