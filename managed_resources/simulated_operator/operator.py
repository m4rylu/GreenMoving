import configparser
import json
import psycopg2
from paho import mqtt

config = configparser.ConfigParser()
config.read('configuration/config.ini')

HOST = config.get('mqtt', 'host')
PORT = config.getint('mqtt', 'port')

SQL_HOST = "postgres_sql"
SQL_USER = "admin"
SQL_DB = "static_db"
SQL_PASSWORD = "adminadmin"

OPERATOR_TOPIC = config.get('mqtt', 'operator_topic')

station_loc = {}

conn = psycopg2.connect(
    host=SQL_HOST,
    database=SQL_DB,
    user=SQL_USER,
    password=SQL_PASSWORD
)
cur = conn.cursor()

client_mqtt = mqtt.Client(client_id="Operator")
client_mqtt.connect(HOST, PORT, 60)
client_mqtt.loop_start()


cur.execute("SELECT id, lat_s, lon_s, address, total_power FROM stations_locations")
rows = cur.fetchall()

for row in rows:
   s_id = row[0]  # Il primo elemento è l'ID (la nostra chiave)
   station_loc[s_id] = {
       "lat": row[1],
       "lon": row[2],
       "address": row[3],
       "total_power": row[4]
   }
   cur.close()

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected with result code "+str(rc))

    client.subscribe(OPERATOR_TOPIC)

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    topic = msg.topic.split("/")
    if topic[1] == "operators":
        request = payload["request"]
        #operator take the bike to the station and connect it
        if request=="CHARGE":
            bike_id = payload["bike_id"]
            station_id = payload["station_id"]
            print(f"Ricevuta richiesta di ricaricare bici {bike_id}")
            print(f"Contatto bici")
            payload1 = {
                "request": request,
                "lat": station_loc[station_id]["lat"],
                "lon": station_loc[station_id]["lon"],
            }
            client_mqtt.publish(f"ebike/bikes/{bike_id}/commands", json.dumps(payload1))
            print("Contatto stazione")
            payload1 = {
                "request": "CONNECT",
                "slot": payload["slot"],
                "bike_id": bike_id,
            }
            client_mqtt.publish(f"ebike/stations/{station_id}/request", json.dumps(payload1))
