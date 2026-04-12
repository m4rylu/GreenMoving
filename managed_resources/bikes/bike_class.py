import time
import configparser
import random
import json
import paho.mqtt.client as mqtt

config = configparser.ConfigParser()
config.read('configuration/config.ini')

HOST = config.get('mqtt', 'host')
PORT = config.getint('mqtt', 'port')

UPDATE_RATE = config.getfloat('update_rate', 'bikes_update_rate')
BIKE_AVAILABILITY_TRESHOLD = config.getint('system', 'bike_availability_treshold')

MAX_LAT = config.getfloat('coordinates', 'max_latitude')
MIN_LAT = config.getfloat('coordinates', 'min_latitude')
MAX_LON = config.getfloat('coordinates', 'max_longitude')
MIN_LON = config.getfloat('coordinates', 'min_longitude')


class Bike:
    def __init__(self, bike_id:str):
        self.id = bike_id
        self.lat = round(random.uniform(MIN_LAT, MAX_LAT),4)
        self.lon = round(random.uniform(MIN_LON,MAX_LON),4)
        self.battery = random.randint(0, 100)
        self.locked = True
        self.is_charging = False
        self.charge_rate = 0

        # Topic specifici
        self.telemetry_topic = f"ebike/bikes/{self.id}/telemetry"
        self.command_topic = f"ebike/bikes/{self.id}/commands"

        self.client = mqtt.Client(client_id=self.id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(HOST, PORT, 60)
        self.client.loop_start()


    def on_connect(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        client.subscribe(self.command_topic)
        client.subscribe(f"ebike/bikes/{self.id}/commands")

    def on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload.decode())
        cmd = payload.get("request")
        print(f"RICEVUTO COMANDO: {cmd}")
        if cmd == "UNLOCK":
            self.actuator_lock(False)
        elif cmd == "LOCK":
            self.actuator_lock(True)
        elif cmd == "CHARGE":
            self.is_charging = True
            self.charge_rate = 0
            self.lat = float(payload.get("lat"))
            self.lon = float(payload.get("lon"))
        elif cmd == "BALANCE":
            self.charge_rate=payload.get("rate")


    def actuator_lock(self, b:bool):
        self.locked = b
        if not b: 
            self.is_charging = False


    def sensor_gps(self):
        if not self.locked:
            # SIMULATION
            # of human movement with bike
            self.lat += random.uniform(-0.001, 0.001)
            self.lon += random.uniform(-0.001, 0.001)


    def sensor_battery(self):
        if self.is_charging:
            self.battery = min(self.battery + self.charge_rate, 100)
        elif not self.locked:
            self.battery = max(0, self.battery - 5) # in uso
        elif self.locked:
            self.battery = max(0,self.battery - 1) # bloccata
        

    def sensor_current(self):
        return


    def send_state(self):
        state = {
            "battery": self.battery,
            "motor_locked": self.locked,
            "is_charging": self.is_charging,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4)
        }
        payload = {
            "telemetry":state
        }
        print(f"Bici: {self.id}, Batteria: {self.battery}, Latitude: {self.lat}, Longitude: {self.lon}")
        self.client.publish(f"ebike/bikes/{self.id}/telemetry", json.dumps(payload))

    def simulation(self):
        while True:
            self.sensor_gps()
            self.sensor_battery()
            self.send_state()
            time.sleep(UPDATE_RATE)
