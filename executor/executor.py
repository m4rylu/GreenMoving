import json

import paho.mqtt.client as mqtt
import psycopg2
import time
import configparser
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone

config = configparser.ConfigParser()
config.read('configuration/config.ini')

TOKEN = config.get('influx_db', 'token')
ORG = config.get('influx_db', 'org')
BUCKET = config.get('influx_db', 'bucket')
URL = config.get('influx_db', 'url')

SQL_HOST = "postgres_sql"
SQL_USER = "admin"
SQL_DB = "static_db"
SQL_PASSWORD = "adminadmin"

HOST = config.get('mqtt', 'host')
PORT = config.getint('mqtt', 'port')

UPDATE_RATE = config.getint('update_rate', 'executor_update_rate')

STATION_COMMAND_TOPIC = config.get('mqtt_topics', 'station_command_topic')
OPERATOR_TOPIC = config.get('mqtt_topics', 'operator_topic')

last_time=datetime.now(timezone.utc)
last_time_1=datetime.now(timezone.utc)

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected with result code "+str(rc))
    client.subscribe(STATION_COMMAND_TOPIC)


def retrieve_plan_data():
    global last_time

    flux_query = f'''
        from(bucket: "{BUCKET}")
        |> range(start: -1d) 
        |> filter(fn: (r) => r["_measurement"] == "plan_bikes")
        |> last()
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    tables = query_api.query(query=flux_query, org=ORG)
    latest_time = last_time

    for table in tables:
        for record in table.records:
            record_time = record.get_time()

            if record_time > last_time:
                bike_id = record.values.get("bike_id")
                event = record.values.get("event")

                if event == "AVAILABLE":
                    minutes = record.values.get("minutes")
                    price = record.values.get("price")

                    print(f"[EXECUTOR] Pubblico bici {bike_id}: {minutes} min a {price}€")

                    sql_query = """
                    INSERT INTO available_bikes (id, minutes, price)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) 
                    DO UPDATE SET 
                        minutes = EXCLUDED.minutes,
                        price = EXCLUDED.price;
                    """
                    cur.execute(sql_query, (bike_id, minutes, price))
                    conn.commit()

                elif event == "NOT AVAILABLE":
                    print(f"[EXECUTOR] Rimuovo bici {bike_id} perché non disponibile")

                    sql_query = "DELETE FROM available_bikes WHERE id = %s;"
                    cur.execute(sql_query, (bike_id,))
                    conn.commit()

                if record_time > latest_time:
                    latest_time = record_time

    last_time = latest_time

def retrieve_bike_recharging():
    global last_time_1

    flux_query = f'''
        from(bucket: "{BUCKET}")
        |> range(start: -1d) 
        |> filter(fn: (r) => r["_measurement"] == "plan_bikes_recharging")
        |> last()
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    tables = query_api.query(query=flux_query, org=ORG)
    latest_time = last_time_1

    for table in tables:
        for record in table.records:
            record_time = record.get_time()

            if record_time > last_time_1:
                bike_id = record.values.get("bike_id")
                station = record.values.get("station")
                slot = record.values.get("slot")

                payload = {
                    "request": "CHARGE",
                    "slot": slot,
                    "bike_id": bike_id,
                    "station_id": station,
                }
                print(f"BIKE_ID {bike_id}")
                # avvisa l'operatore
                client_mqtt.publish(OPERATOR_TOPIC, json.dumps(payload))
                print(f"mando richiesta operatore di ricaricare {bike_id} in {station} at {slot}")

                if record_time > latest_time:
                    latest_time = record_time

    last_time_1 = latest_time



def execute():
    retrieve_plan_data()
    retrieve_bike_recharging()

if __name__ == "__main__":

    time.sleep(10)

    client_db = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client_db.query_api()
    write_api = client_db.write_api(write_options=SYNCHRONOUS)

    client_mqtt = mqtt.Client(client_id="Executor")
    client_mqtt.connect(HOST, PORT, 60)
    client_mqtt.loop_start()

    conn = psycopg2.connect(
        host=SQL_HOST,
        database=SQL_DB,
        user=SQL_USER,
        password=SQL_PASSWORD
    )
    cur = conn.cursor()

    while True:
        execute()
        time.sleep(UPDATE_RATE)
