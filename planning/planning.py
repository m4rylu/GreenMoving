import time
import configparser

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

ANALYSIS_TOPIC = "mapek/analysis"
HOST = "localhost"
PORT = 8086

stations={}
station_knowledge={}
bikes_history={}
last_time = datetime.now(timezone.utc)


bikes = {}

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
            bikes[bike_id] = {"battery": battery, "locked": locked, "is_charging": is_charging}

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



def retrieve_bike_analysis():
    global last_time
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
                    print("received not available event")
                    point = Point("plan_bikes") \
                        .tag("bike_id", bike_id) \
                        .field("event", "NOT AVAILABLE")

                    write_api.write(bucket=BUCKET, record=point)

                elif event=="LOW_BATTERY":
                    print("received low battery event")
                    point = Point("plan_bikes") \
                        .tag("bike_id", bike_id) \
                        .field("event", "NOT AVAILABLE")
                    write_api.write(bucket=BUCKET, record=point)

                    s, sl = plan_bike_recharging()
                    point = Point("plan_bikes_recharging") \
                        .tag("bike_id", bike_id) \
                        .field("station", s) \
                        .field("slot", sl) \

                    write_api.write(bucket=BUCKET, record=point)

                    print(f"bike {bike_id} shuold be recharged at station {s} slot {sl}")

                if record_time > current_max_time:
                    current_max_time = record_time

                last_time = current_max_time


def do_planning():
    retrieve_bike_telemetry()
    retrieve_station_status()
    retrieve_bike_analysis()

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
