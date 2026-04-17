import paho.mqtt.client as mqtt
import json
import os
import jwt
import configparser

from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, render_template, request, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


config = configparser.ConfigParser()
config.read('configuration/config.ini')

#MQTT configuration
MQTT_HOST = config.get('mqtt', 'host')
MQTT_PORT = config.getint('mqtt', 'port')
BOOKINGS_TOPIC = config.get('mqtt_topics', 'bookings_topic')

app = Flask(__name__)
SECRET_KEY = 'una_chiave_segreta_molto_sicura'

# Postegres SQL configuration
DB_URL = os.getenv('DATABASE_URL', 'postgresql://admin:adminadmin@postgres_sql:5432/static_db')
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# -- FUNCTION --

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


def log_reservation_to_mqtt(user_id, bike_id, price):
    payload = {
        "user_id": str(user_id),
        "bike_id": str(bike_id),
        "event": "BOOKED",
        "price": float(price)
    }

    # Client MQTT "usa e getta" per la pubblicazione
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.publish(BOOKINGS_TOPIC, json.dumps(payload))
    client.disconnect()
    print(f"📡 Messaggio MQTT inviato: {payload}")

def request_end_ride_mqtt(bike_id, user_id):
    payload = {
        "user_id": str(user_id),
        "bike_id": str(bike_id),
        "event": "END_RIDE"
    }
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.publish(BOOKINGS_TOPIC, json.dumps(payload))
    client.disconnect()
    print(f"🛑 Richiesta FINE CORSA inviata via MQTT: {payload}")



# -- DB CLASS --

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

class Ride(db.Model):
    __tablename__ = 'rides'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    bike_id = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='active')


# -- ROUTES --

@app.route('/')
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

@app.route('/dashboard', methods=['GET', 'POST'])
@token_required
def dashboard(current_user_id):
    bikes = AvailableBike.query.all()
    user = User.query.get(current_user_id)
    return render_template('dashboard.html', bikes=bikes, username=user.username)


# --- AGGIUNGI O MODIFICA QUESTE ROTTE ---

@app.route('/reserve/<bike_id>/<price>', methods=['GET'])
@token_required
def reserve_bike(current_user_id, bike_id, price):
    log_reservation_to_mqtt(current_user_id, bike_id, price)

    return redirect(url_for('my_bookings', pending_bike_id=bike_id))


@app.route('/my-bookings')
@token_required
def my_bookings(current_user_id):
    user = User.query.get(current_user_id)

    user_rides = Ride.query.filter_by(user_id=str(current_user_id))\
                           .order_by(Ride.start_time.desc()).all()

    confirmed_bookings = []
    for r in user_rides:
        confirmed_bookings.append({
            "id": r.id,
            "bike_id": r.bike_id,
            "time": r.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": r.status
        })

    pending = request.args.get('pending_bike_id')

    return render_template('reservations.html',
                           username=user.username,
                           confirmed=confirmed_bookings,
                           pending=pending)

@app.route('/api/check_reservation/<bike_id>')
@token_required
def check_reservation(current_user_id, bike_id):
    # Cerchiamo se esiste una corsa 'active' per questo utente e questa bici
    ride = Ride.query.filter_by(
        user_id=str(current_user_id),
        bike_id=str(bike_id),
        status='active'
    ).first()

    if ride:
        return {"status": "SUCCESS"}
    else:
        return {"status": "WAITING"}


@app.route('/end-ride/<int:ride_id>')
@token_required
def end_ride(current_user_id, ride_id):
    ride = Ride.query.filter_by(id=ride_id, user_id=str(current_user_id)).first()

    if ride and ride.status == 'active':
        request_end_ride_mqtt(ride.bike_id, current_user_id)

        return redirect(url_for('my_bookings', msg="terminating"))

    return redirect(url_for('my_bookings', error="invalid_ride"))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)