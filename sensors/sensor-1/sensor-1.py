import configparser
import json
import random
import time
import uuid
import paho.mqtt.client as mqtt

config = configparser.ConfigParser()
config.read('config.ini')

arrival_chance = config.getfloat('SIMULATION', 'CHANCE_ARRIVO')
max_charge = config.getint('SIMULATION', 'CARICA_MASSIMA')
time_interval = config.getint('SIMULATION', 'INTERVALLO_TEMPO')
event_probability = config.getfloat('SIMULATION', 'RANDOM_EVENT_PROBABILITY')
broker_address = config.get('BROKER', 'ADDRESS')
broker_port = config.getint('BROKER', 'PORT')
broker_topic = config.get('BROKER', 'TOPIC')
client_id = config.get('BROKER', 'CLIENT_ID')


# Dizionario per gestire le bici: {id_bici: carica_attuale}
bici_in_carica = {"b3f5d587":15}

def genera_nuova_bici():
    """Crea una nuova bici con un ID univoco e una carica iniziale bassa."""
    id_bici = str(uuid.uuid4())[:8] # ID breve per leggibilità
    carica_iniziale = random.randint(5, 20)
    return id_bici, carica_iniziale

def on_connect(client, userdata, flags, rc):
    if rc==0:
        print("Connected")
    else:
        print("Failed to connect")

def on_message(client, userdata, message):
    print(f"Received message on {message.topic}: {message.payload.decode()}")

client = mqtt.Client()
client.on_connect
client.on_message
client.connect(broker_address, port=broker_port)
client.loop_start()

while True:
    print(f"\n[AGGIORNAMENTO CICLO - {time.strftime('%H:%M:%S')}]")

        # 1. Simulazione Arrivo Nuova Bici
    if random.random() < arrival_chance:
        nuovo_id, carica = genera_nuova_bici()
        bici_in_carica[nuovo_id] = carica
        print(f"🚲 NUOVO ARRIVO: Bici [{nuovo_id}] collegata con {carica}% di carica.")

    
    if not bici_in_carica:
        print("... Nessuna bici in carica al momento.")

    for id_bici in list(bici_in_carica.keys()):
        # random increment
        incremento = random.randint(1, 8) 
            
        # blackout event or surplus charge
        evento_raro = random.random()
        if evento_raro < event_probability:
            incremento = 0
            print(f"⚠️ CALO DI TENSIONE sulla postazione [{id_bici}]! Carica ferma.")
        elif evento_raro > 1.0-event_probability:
                incremento += 10
                print(f"⚡ SURPLUS ENERGETICO! Carica rapida per [{id_bici}].")

        bici_in_carica[id_bici] += incremento
            
        # Controllo se ha finito la carica
        if bici_in_carica[id_bici] >= max_charge:
            bici_in_carica[id_bici] = max_charge
            print(f"✅ Bici [{id_bici}] CARICA COMPLETATA (100%).")
        else:
            print(f"   - Bici [{id_bici}]: {bici_in_carica[id_bici]}% (+{incremento}%)")

        data = {}

        for bike_id, charge_level in bici_in_carica.items():
            payload = {
                "id": bike_id,
                "level": charge_level,
                }

        client.publish(broker_topic, json.dumps(payload))

    time.sleep(time_interval)