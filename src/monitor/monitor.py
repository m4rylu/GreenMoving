import configparser
import paho.mqtt.client as mqtt
import json
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

config = configparser.ConfigParser()
config.read('configuration/config.ini')

UPDATE_RATE = config.getint('update_rate', 'monitor_update_rate')
N_SLOT = config.getint('system', 'n_slot_x_station')

TOKEN = config.get('influx_db', 'token')
ORG = config.get('influx_db', 'org')
BUCKET = config.get('influx_db', 'bucket')
URL = config.get('influx_db', 'url')

HOST = config.get('mqtt', 'host')
PORT = config.getint('mqtt', 'port')

BIKE_TOPIC = config.get('mqtt_topics', 'bike_topic')
STATION_TOPIC = config.get('mqtt_topics', 'station_topic')
BOOKINGS_TOPIC = config.get('mqtt_topics', 'bookings_topic')


def send_data_bikes(payload, bike_id):
    point = Point("bikes") \
        .tag("bike_id", bike_id)
    for key, value in payload.items():
        point.field(key, value)

    write_api.write(bucket=BUCKET, record=point)

def send_data_station(payload, station_id):
    print(f"payload: {payload}")
    for key, value in payload.items():
        point = Point("station") \
        .tag("station_id", station_id) \
        .tag("slot_id", key) \
        .field(f"status", value["status"]) \
        .field(f"rate", value["rate"])

        write_api.write(bucket=BUCKET, record=point)

def send_data_bookings(payload):
    point = Point("bookings") \
            .tag("bike_id", payload.get("bike_id")) \
            .field("user_id", payload.get("user_id")) \
            .field("event", payload.get("event")) \
            .field("price", payload.get("price"))

    write_api.write(bucket=BUCKET, record=point)




def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected with result code "+str(rc))
    client.subscribe(BIKE_TOPIC)
    client.subscribe(STATION_TOPIC)
    client.subscribe(BOOKINGS_TOPIC)

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    topic = msg.topic.split("/")
    if topic[1] == "bikes":
        print("msg_topic", msg.topic)
        print("msg payload", msg.payload)
        bike_id = msg.topic.split("/")[2]
        send_data_bikes(payload["telemetry"], bike_id)
    if topic[1] == "stations":
        print("msg_topic", msg.topic)
        print("msg payload", msg.payload)
        station_id = msg.topic.split("/")[2]
        send_data_station(payload["slots"], station_id)
    if topic[1] == "bookings":
        print("msg_topic", msg.topic)
        print("msg payload", msg.payload)
        send_data_bookings(payload)

if __name__ == "__main__":
    time.sleep(7)
    client = mqtt.Client(client_id="Monitor")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(HOST, PORT, 60)
    client.loop_start()

    client_db = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    write_api = client_db.write_api(write_options=SYNCHRONOUS)

    while True:
        time.sleep(UPDATE_RATE)
