"""Simule un ESP32 : envoie des mesures au serveur pour tester sans matériel.

Utilisation (le serveur doit tourner) :
    python simulateur.py            -> mesures normales, avec un départ de feu de temps en temps
    python simulateur.py --feu      -> envoie tout de suite une détection de flamme
"""

import json
import random
import sys
import time
import urllib.request

URL = "http://127.0.0.1:5000/api/data"


def send(measure):
    req = urllib.request.Request(
        URL, data=json.dumps(measure).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read())
    alerts = f"  -> ALERTE {result['alerts']}" if result["alerts"] else ""
    print(f"Envoyé : {measure}{alerts}")


def measure(fire=False, gas_leak=False):
    return {
        "device_id": 1,
        "temperature": round(random.uniform(26, 29) + (15 if fire else 0), 1),
        "humidity": round(random.uniform(52, 60), 1),
        "gaz": random.randint(380, 520) if gas_leak or fire else random.randint(35, 60),
        "flamme": 1 if fire else 0,
    }


if __name__ == "__main__":
    if "--feu" in sys.argv:
        send(measure(fire=True))
        sys.exit()

    print("Simulation en cours (Ctrl+C pour arrêter)...")
    step = 0
    while True:
        step += 1
        cycle = step % 40
        send(measure(fire=30 <= cycle < 34, gas_leak=20 <= cycle < 24))
        time.sleep(2)
