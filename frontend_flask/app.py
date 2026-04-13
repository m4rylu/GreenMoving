from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, render_template, request, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from werkzeug.security import generate_password_hash, check_password_hash

import os
import jwt



# InfluxDB configuration (aggiungere il riferimento al file config.ini)
INFLUX_URL = "http://influxdb:8086"
INFLUX_TOKEN = "9UAPy4qDu16TQSUe4G9EN88rzsnC1srqrhgwu4Kxg9asMCxLdkCq_NgZzUp2gpnAfSj5W-XTzjeIUEsA23CiIw=="
INFLUX_ORG = "GreenMoving"
INFLUX_BUCKET = "bike_monitoring"

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = influx_client.query_api()
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

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


def log_reservation_to_influx(user_id, bike_id):
    point = Point("bookings") \
        .tag("user_id", user_id) \
        .tag("bike_id", bike_id) \
        .field("val", 1)

    write_api.write(bucket=INFLUX_BUCKET, record=point)



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

@app.route('/reserve/<bike_id>', methods=['GET'])
@token_required
def reserve_bike(current_user_id, bike_id):
    log_reservation_to_influx(current_user_id, bike_id)

    return redirect(url_for('my_bookings', pending_bike_id=bike_id))


@app.route('/my-bookings')
@token_required
def my_bookings(current_user_id):
    user = User.query.get(current_user_id)

    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
    |> range(start: -1d)
    |> filter(fn: (r) => r["_measurement"] == "bookings_completed")
    |> filter(fn: (r) => r["user_id"] == "{current_user_id}")
    |> sort(columns: ["_time"], desc: true)
    '''
    result = query_api.query(query)

    confirmed_bookings = []
    for table in result:
        for record in table.records:
            confirmed_bookings.append({
                "bike_id": record.values.get("bike_id"),
                "time": record.get_time()
            })

    pending = request.args.get('pending_bike_id')

    return render_template('reservations.html',
                           username=user.username,
                           confirmed=confirmed_bookings,
                           pending=pending)

@app.route('/api/check_reservation/<bike_id>')
@token_required # Aggiungiamo la protezione anche qui
def check_reservation(current_user_id, bike_id):
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
    |> range(start: -1m)
    |> filter(fn: (r) => r["_measurement"] == "bookings_completed")
    |> filter(fn: (r) => r["bike_id"] == "{bike_id}")
    |> filter(fn: (r) => r["user_id"] == "{current_user_id}")
    |> last()
    '''
    result = query_api.query(query)
    return {"status": "SUCCESS"} if any(table.records for table in result) else {"status": "WAITING"}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)