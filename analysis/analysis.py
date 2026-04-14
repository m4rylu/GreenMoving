import time
import configparser
from datetime import timezone, datetime

import psycopg2
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

config = configparser.ConfigParser()
config.read('configuration/config.ini')

TOKEN = config.get('influx_db', 'token')
ORG = config.get('influx_db', 'org')
BUCKET = config.get('influx_db', 'bucket')
URL = config.get('influx_db', 'url')

BIKE_MOVEMENT_TRESHOLD = config.getfloat('system', 'bike_movement_threshold')
N_SLOT = config.getint('system', 'n_slot_x_station')
AVAILABILITY_THRESHOLD = config.getfloat('system', 'bike_availability_treshold')

MIN_LAT = config.getfloat('coordinates', 'min_latitude')
MAX_LAT = config.getfloat('coordinates', 'max_latitude')
MIN_LON = config.getfloat('coordinates', 'min_longitude')
MAX_LON = config.getfloat('coordinates', 'max_longitude')

UPDATE_RATE = config.getint('update_rate', 'analysis_update_rate')

bikes = {}
last_bike_analysis = {}
bookings = []

last_time = datetime.now(timezone.utc)




def retrieve_bike_telemetry():
    global bookings
    flux_query_bikes = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "bikes")
      |> last()
      |> sort(columns: ["_time"], desc: false)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    # BIKES ANALYSIS
    tables = query_api.query(query=flux_query_bikes, org=ORG)
    for table in tables:
        for record in table.records:

            bike_id = record.values.get("bike_id")
            battery = record.values.get("battery")
            locked = record.values.get("motor_locked")
            is_charging = record.values.get("is_charging")
            lat = record.values.get("lat")
            lon = record.values.get("lon")

            active_alert = "IN_USE"

            if battery >= AVAILABILITY_THRESHOLD and locked:
                booking_found = next((b for b in bookings if b[0] == bike_id), None)
                if booking_found:
                    active_alert = "BOOKED"
                else:
                    active_alert = "AVAILABLE"

            elif battery < AVAILABILITY_THRESHOLD and not is_charging:
                active_alert = "LOW_BATTERY"

            elif (MIN_LAT > lat or MAX_LAT < lat) or (MIN_LON > lon or MAX_LON < lon):
                    active_alert = "OUT_OF_RANGE"


            if last_bike_analysis.get(bike_id) != active_alert:
                print(f"Bike {bike_id} is {active_alert}")
                point = Point("bike_analysis") \
                        .tag("bike_id", bike_id) \
                        .field("event", active_alert)

                write_api.write(bucket=BUCKET, record=point)

            last_bike_analysis[bike_id] = active_alert

def retrieve_station_status():
    flux_query_bikes = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1d)
      |> filter(fn: (r) => r["_measurement"] == "station")
      |> last()
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    # STATION ANALYSIS
    station = {}
    tables = query_api.query(query=flux_query_bikes, org=ORG)
    for table in tables:
        for record in table.records:
            station_id = record.values.get("station_id")
            slot_id = record.values.get("slot_id")

            if station_id not in station:
                station[station_id] = {}

            station[station_id][slot_id] = {
                "status": record.values.get("status"),
                "rate": record.values.get("rate")
            }

    for s_id , slot_ids in station.items():

        all_statuses = [data["status"] for data in slot_ids.values()]

        if all(s == "empty" for s in all_statuses):
            active_alert = "EMPTY STATION"
        elif all(s != "empty" for s in all_statuses):
            active_alert = "FULL STATION"
        else:
            active_alert = "NORMAL"

        if active_alert:
            if last_bike_analysis.get(s_id) != active_alert:
                point = Point("station_analysis") \
                    .tag("station_id", s_id) \
                    .field("event", active_alert)

                write_api.write(bucket=BUCKET, record=point)
            last_bike_analysis[s_id] = active_alert


def retrieve_bookings():
    global last_time
    global bookings
    current_max_time = last_time
    now = datetime.now(timezone.utc)

    bookings = [b for b in bookings if (now - b[2]).total_seconds() < 120]
    flux_query_bikes = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1d)
          |> filter(fn: (r) => r["_measurement"] == "bookings")
          |> last()
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

    tables = query_api.query(query=flux_query_bikes, org=ORG)
    for table in tables:
        for record in table.records:
            record_time = record.get_time()
            if record_time > last_time:
                user_id = record.values.get("user_id")
                bike_id = record.values.get("bike_id")

                if not any(bike[0] == bike_id for bike in bookings):
                    bookings.append((bike_id,user_id, record_time))

                if record_time > current_max_time:
                    current_max_time = record_time

    last_time = current_max_time

def do_analysis():
    retrieve_bookings()
    retrieve_bike_telemetry()
    retrieve_station_status()



if __name__ == "__main__":
    time.sleep(15)

    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    conn_params = {
        "host": "postgres_sql",
        "database": "static_db",
        "user": "admin",
        "password": "adminadmin"
    }
    conn=psycopg2.connect(**conn_params)
    cur = conn.cursor()

    while True:
        do_analysis()
        time.sleep(UPDATE_RATE)
