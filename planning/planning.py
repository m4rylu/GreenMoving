import time
import configparser
import psycopg2

from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

config = configparser.ConfigParser()
config.read('configuration/config.ini')

TOKEN = config.get('influx_db', 'token')
ORG = config.get('influx_db', 'org')
BUCKET = config.get('influx_db', 'bucket')
URL = config.get('influx_db', 'url')

N_SLOT = config.getint('system', 'n_slot_x_station')
RESET_TASK_TIME = config.getint('system', 'reset_task_time')
UPDATE_RATE = config.getint('update_rate', 'planning_update_rate')
AVAILABILITY_THRESHOLD = config.getint('system', 'bike_availability_treshold')

ANALYSIS_TOPIC = "mapek/analysis"
HOST = "localhost"
PORT = 8086

SQL_HOST = "postgres_sql"
SQL_USER = "admin"
SQL_DB = "static_db"
SQL_PASSWORD = "adminadmin"

time.sleep(10)

conn = psycopg2.connect(
        host=SQL_HOST,
        database=SQL_DB,
        user=SQL_USER,
        password=SQL_PASSWORD
    )
cur = conn.cursor()

stations={}
station_knowledge={}
empty_stations=[]
bikes_history={}
bikes = {}
bookings = []


last_time = datetime.now(timezone.utc)
last_time_1 = datetime.now(timezone.utc)

def plan_bike_recharging():
    global stations
    val = None
    stat = None
    for s in stations:
        c = sum(stations[s][slot]["status"]=="empty" for slot in stations[s])
        print("COUNT", c)
        if (val is None) or (c>val):
            val = c
            stat = s

    for g in stations[stat]:
        if stations[stat][g]["status"] == "empty":
            stations[stat][g]["status"] = "RESERVED"
            return stat, g
    return None, None



def retrieve_bike_telemetry():
    query_bikes = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -30d)
          |> filter(fn: (r) => r["_measurement"] == "bikes")
          |> last()
          |> sort(columns: ["_time"], desc: false)
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
    # BIKES ANALYSIS
    tables = query_api.query(query=query_bikes, org=ORG)
    for table in tables:
        for record in table.records:
            bike_id = record.values.get("bike_id")
            battery = record.values.get("battery")
            locked = record.values.get("motor_locked")
            is_charging = record.values.get("is_charging")
            lat = record.values.get("lat")
            lon = record.values.get("lon")
            bikes[bike_id] = {"battery": battery, "locked": locked, "is_charging": is_charging, "lat": lat, "lon": lon}

def retrieve_station_status():
    global stations
    flux_query_bikes = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1d)
      |> filter(fn: (r) => r["_measurement"] == "station")
      |> last()
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    # STATION ANALYSIS
    tables = query_api.query(query=flux_query_bikes, org=ORG)
    for table in tables:
        for record in table.records:
            station_id = record.values.get("station_id")
            slot_id = record.values.get("slot_id")

            if station_id not in stations:
                stations[station_id] = {}

            if slot_id not in stations[station_id]:
                stations[station_id][slot_id] = {}

            stations[station_id][slot_id]["status"]=record.values.get(f"status")
            stations[station_id][slot_id]["rate"]=record.values.get(f"rate")
    for s in stations:
        print(f"station with key {s} has values {stations[s]}")

def retrieve_empty_station():
    global empty_stations
    flux_query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1d)
      |> filter(fn: (r) => r["_measurement"] == "station_analysis")
      |> last()
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    tables = query_api.query(query=flux_query, org=ORG)
    empty_stations = []
    for table in tables:
        for record in table.records:
            station_id = record.values.get("station_id")
            event = record.values.get("event")

            if event == "EMPTY STATION":
                empty_stations.append(station_id)
    print(f"empty station has values {empty_stations}")


def retrieve_bike_analysis():
    global last_time
    global bookings
    query = f'''
    from(bucket: "{BUCKET}")
    |> range(start: -1d)
    |> filter(fn: (r) => r["_measurement"] == "bike_analysis")
    |> last()
    |> sort(columns: ["_time"], desc: false)
    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    tables = query_api.query(query=query, org=ORG)
    current_max_time = last_time
    for table in tables:
        for record in table.records:
            record_time = record.get_time()
            if record_time > last_time:
                bike_id = record.values.get("bike_id")
                event = record.values.get("event")
                if event=="AVAILABLE":
                    print("received available event")
                    minutes = int(bikes[bike_id]["battery"] * 2)
                    price = 20
                    point = Point("plan_bikes") \
                        .tag("bike_id", bike_id) \
                        .field("event", "AVAILABLE") \
                        .field("minutes", minutes) \
                        .field("price", price)

                    write_api.write(bucket=BUCKET, record=point)

                elif event=="BOOKED":
                    user_id = record.values.get("user_id")
                    s = "empty"
                    sl = "empty"
                    found = False

                    for station in stations:
                        for slot in stations[station]:
                            if stations[station][slot]["status"] == bike_id:
                                s = station
                                sl = slot
                                found = True
                                break
                        if found:
                            break

                    point = Point("plan_bikes") \
                        .tag("bike_id", bike_id) \
                        .field("event", "BOOKED") \
                        .field("station", s) \
                        .field("slot", sl) \
                        .field("user_id", user_id)

                    write_api.write(bucket=BUCKET, record=point)


                    sql_query = """
                    INSERT INTO rides (
                        user_id, bike_id, start_time, end_time, start_lat, start_lon, 
                        end_lat, end_lon, start_battery, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cur.execute(sql_query, (
                        record.values.get("user_id"),
                        bike_id,
                        datetime.now(timezone.utc),
                        None,
                        bikes[bike_id]["lat"],
                        bikes[bike_id]["lon"],
                        None,
                        None,
                        bikes[bike_id]["battery"],
                        "active"
                    ))
                    conn.commit()

                elif event=="LOW_BATTERY":
                    print("received low battery event")
                    point = Point("plan_bikes") \
                        .tag("bike_id", bike_id) \
                        .field("event", "LOW_BATTERY")
                    write_api.write(bucket=BUCKET, record=point)

                    s, sl = plan_bike_recharging()
                    point = Point("plan_bikes_recharging") \
                        .tag("bike_id", bike_id) \
                        .field("station", s) \
                        .field("slot", sl) \

                    write_api.write(bucket=BUCKET, record=point)

                    print(f"bike {bike_id} should be recharged at station {s} slot {sl}")

                if record_time > current_max_time:
                    current_max_time = record_time

                last_time = current_max_time

def plan_station_rate():
    for station in stations:
        if station in empty_stations:
            continue

        high_priority = []
        low_priority = []
        total_power = 5
        station_to_update  = {slot:0 for slot in stations[station]}


        for slot in stations[station]:
            if stations[station][slot]["status"] == "empty" or stations[station][slot]["status"] == "RESERVED":
                continue

            bike_to_schedule = stations[station][slot]["status"]
            if bikes[bike_to_schedule]["battery"] < 100:
                if bikes[bike_to_schedule]["battery"] < AVAILABILITY_THRESHOLD:
                    high_priority.append(slot)
                else:
                    low_priority.append(slot)

            weight_high = 3
            weight_low = 1

            total_weight = (len(high_priority) * weight_high) + \
                            (len(low_priority) * weight_low)

            if total_weight > 0:
                unit_rate = total_power / total_weight

                for s in high_priority:
                    station_to_update[s] = int(round(unit_rate * weight_high, 0))

                for s in low_priority:
                    station_to_update[s] = int(round(unit_rate * weight_low, 0))

            print(f"Stazioneeeeeeeeeeeee {station}: {station_to_update}")

            point = Point("plan_station_rate").tag("station", station)
            for slot_name, rate_value in station_to_update.items():
                point.field(slot_name, rate_value)
            write_api.write(bucket=BUCKET, record=point)


def do_planning():
    retrieve_bike_telemetry()
    retrieve_station_status()
    retrieve_empty_station()
    retrieve_bike_analysis()
    plan_station_rate()

if __name__ == "__main__":
    time.sleep(10)

    #client = mqtt.Client(client_id="Monitor")
    #client.on_connect = on_connect
    #client.on_message = on_message
    #client.connect(HOST, PORT, 60)
    #client.loop_start()

    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    #retrieve_station_knowledge()
    while True:
        do_planning()
        time.sleep(UPDATE_RATE)
