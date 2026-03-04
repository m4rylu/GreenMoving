from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, render_template, request, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import jwt

app = Flask(__name__)
SECRET_KEY = 'una_chiave_segreta_molto_sicura'  # Necessaria per gestire i messaggi flash

DB_URL = os.getenv('DATABASE_URL', 'postgresql://admin:adminadmin@postgres_sql:5432/static_db')
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('session_token')

        if not token:
            return redirect(url_for('login'))

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            current_user_id = data['user_id']
        except Exception as e:
            return redirect(url_for('login'))

        return f(current_user_id, *args, **kwargs)
    return decorated



class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class AvailableBike(db.Model):
    __tablename__ = 'available_bikes'
    id = db.Column(db.String(50), primary_key=True)
    minutes = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)

# -- ROUTES --

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')

        # error user exists
        if User.query.filter_by(username=user).first():
            return "Errore: lo username esiste già!", 400

        # new user
        hashed_pw = generate_password_hash(pw, method='pbkdf2:sha256')
        new_user = User(username=user, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')

        # Cerchiamo l'utente nel DB
        target_user = User.query.filter_by(username=user).first()

        # Verifichiamo se l'utente esiste e se la password coincide
        if target_user and check_password_hash(target_user.password, pw):
            payload = {
                'user_id': target_user.id,
                'exp': datetime.now(timezone.utc) + timedelta(hours=24)
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

            response = make_response(redirect(url_for('dashboard')))
            response.set_cookie('session_token', token, httponly=True)
            return response

        return "Credenziali errate!", 401

    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@token_required
def dashboard(current_user_id):
    bikes = AvailableBike.query.all()
    user = User.query.get(current_user_id)
    return render_template('dashboard.html', bikes=bikes, username=user.username)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)