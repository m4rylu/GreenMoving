import time
import configparser
import psycopg2

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

time.sleep(10)

conn = psycopg2.connect(
        host=SQL_HOST,
        database=SQL_DB,
        user=SQL_USER,
        password=SQL_PASSWORD
    )
cur = conn.cursor()

stations={}
bikes_history={}

static_knowledge = {}
for section in config.sections():
    if section.startswith('S'):
        static_knowledge[section] = {
            "lat": config.getfloat(section, 'lat'),
            "lon": config.getfloat(section, 'lon'),
            "address": config.get(section, 'address'),
            "total_power": config.getint(section, 'total_power')
        }

for s in static_knowledge:
    sql_query = """
    INSERT INTO stations_locations (station_id, lat_s, lon_s, address, total_power)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (station_id) DO UPDATE SET
        lat_s = EXCLUDED.lat_s,
        lon_s = EXCLUDED.lon_s,
        address = EXCLUDED.address,
        total_power = EXCLUDED.total_power;
    """
    cur.execute(sql_query, (
        s,
        static_knowledge[s]["lat"],
        static_knowledge[s]["lon"],
        static_knowledge[s]["address"],
        static_knowledge[s]["total_power"]
    ))
    conn.commit()

