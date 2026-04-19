import os
import time
from charging_station_class import ChargingStation

STATION_ID = os.getenv('STATION_ID', 'Not Exist')

if __name__ == "__main__":
    s = ChargingStation(STATION_ID)
    while True:
        s.send_slots()
        time.sleep(20)