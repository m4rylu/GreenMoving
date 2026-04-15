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

N_SLOT = config.getint('system', 'n_slot_x_station')
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
last_time_2=datetime.now(timezone.utc)

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

                elif event == "LOW_BATTERY":
                    print(f"[EXECUTOR] Rimuovo bici {bike_id} perché non disponibile")

                    sql_query = "DELETE FROM available_bikes WHERE id = %s;"
                    cur.execute(sql_query, (bike_id,))
                    conn.commit()

                elif event == "BOOKED":
                    user_id = record.values.get("user_id")
                    point = Point("bookings_completed").tag("bike_id", bike_id).field("user_id", user_id).field("event", "ACTIVE")
                    write_api.write(bucket=BUCKET, record=point)

                    sql_query = "DELETE FROM available_bikes WHERE id = %s;"
                    cur.execute(sql_query, (bike_id,))
                    conn.commit()

                    payload = {
                        "request": "UNLOCK",
                        }
                    client_mqtt.publish(f"ebike/bikes/{bike_id}/commands", json.dumps(payload))
                    print(f"mando richiesta di sbloccare bici {bike_id}")

                    s = record.values.get("station")
                    sl = record.values.get("slot")

                    if s != "empty" and sl != "empty":
                        payload = {
                        "request" : "DISCONNECT",
                        "slot" : sl
                        }

                        client_mqtt.publish(f"ebike/stations/{s}/request", json.dumps(payload))
                        print(f"mando richiesta di disconnettere bici allo slot {sl}")

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

                client_mqtt.publish(OPERATOR_TOPIC, json.dumps(payload))
                print(f"mando richiesta operatore di ricaricare {bike_id} in {station} at {slot}")

                if record_time > latest_time:
                    latest_time = record_time

    last_time_1 = latest_time

def retrieve_station_rate():
    global last_time_2

    flux_query = f'''
        from(bucket: "{BUCKET}")
        |> range(start: -1d) 
        |> filter(fn: (r) => r["_measurement"] == "plan_station_rate")
        |> last()
        |> drop(columns: ["_start", "_stop", "_measurement"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    tables = query_api.query(query=flux_query, org=ORG)
    latest_time = last_time_2

    for table in tables:
        for record in table.records:
            record_time = record.get_time()

            if record_time > last_time_2:
                station = record.values.get("station")
                for key, value in record.values.items():
                    if (key != "station" and key !="_time" and key !="result" and key != "table") and value is not None:

                        payload = {
                        "request": "BALANCE",
                        "slot": key,
                        "rate": value,
                        }

                        client_mqtt.publish(f"ebike/stations/{station}/request", json.dumps(payload))
                        print(f"mando richiesta di mandare corrente {value} allo slot {key}")

                if record_time > latest_time:
                    latest_time = record_time

    last_time_2 = latest_time



def execute():
    retrieve_plan_data()
    retrieve_bike_recharging()
    retrieve_station_rate()

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
