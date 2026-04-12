import paho.mqtt.client as mqtt
import json
import time
import configparser

config = configparser.ConfigParser()
config.read('configuration/config.ini')

HOST = config.get('mqtt', 'host')
PORT = config.getint('mqtt', 'port')
N_SLOT = config.getint('system', 'n_slot_x_station')



class ChargingStation:
    def __init__(self, s_id):
        self.id = s_id
        self.slots = {}

        for i in range(1,N_SLOT+1):
            self.slots[f"s{i}"] = {"status": "empty", "rate": 0}

        self.topic_request = f"ebike/stations/{self.id}/request"
        self.topic_status = f"ebike/stations/{self.id}/slots"

        # Setup Client Unico
        self.client = mqtt.Client(client_id=self.id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(HOST, PORT, 60)
        self.client.loop_start()


    def send_slots(self):
        payload = {
            "slots": self.slots
        }
        print(f"Aggiornamento: Slot: {self.slots}")
        self.client.publish(self.topic_status, json.dumps(payload))

    def on_connect(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        self.client.subscribe(self.topic_request)

    def on_message(self,client, userdata, msg):
        payload = json.loads(msg.payload.decode())
        type_request = payload["request"]
        slot_id = payload["slot"]
        if type_request == "DISCONNECT":
            slot = payload["slot"]
            self.slots[slot]["status"] = "empty"
            self.slots[slot]["rate"] = 0
        elif type_request == "CONNECT":
            b = payload["bike_id"]
            print(f" AAAAAAAAAAA received request to connect {b} to slot {slot_id}")
            self.slots[slot_id]["status"] = payload["bike_id"]
        elif type_request == "BALANCE":
            slot = payload["slot"]
            rate = payload["rate"]
            print(f" BBBBBBBBBBBBBB ricevuto rate {rate} per slot {slot}")
            self.slots[slot]["rate"] = payload["rate"]
            # SIMULATION
            # notify the charge rate to the bike but this should be done automatically
            b = self.slots[slot]["status"]
            topic_bikes = f"ebike/bikes/{b}/commands"
            payload = {
                "request": "BALANCE",
                "rate": rate,
            }
            self.client.publish(topic_bikes, json.dumps(payload))




