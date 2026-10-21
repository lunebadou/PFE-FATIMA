"""Écoute le broker MQTT en arrière-plan et enregistre chaque mesure de l'ESP32."""

import json
import threading

import paho.mqtt.client as mqtt

from config import MQTT_BROKER, MQTT_PASSWORD, MQTT_PORT, MQTT_TOPIC, MQTT_USER

# État partagé, affiché dans le tableau de bord admin (/api/status)
STATE = {"enabled": False, "connected": False, "last_message": None, "messages": 0, "error": None}

_client = None
_lock = threading.Lock()


def _on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        STATE.update(connected=True, error=None)
        client.subscribe(MQTT_TOPIC)
        print(f"[MQTT] Connecté à {MQTT_BROKER}:{MQTT_PORT}, abonné à « {MQTT_TOPIC} »")
    else:
        STATE.update(connected=False, error=str(reason_code))
        print(f"[MQTT] Connexion refusée : {reason_code}")


def _on_disconnect(client, userdata, flags, reason_code, properties=None):
    STATE["connected"] = False
    print(f"[MQTT] Déconnecté ({reason_code}), nouvelle tentative automatique...")


def _on_message(client, userdata, msg):
    from database import now
    from routes.data import ingest_measurement  # import ici pour éviter une boucle d'imports

    try:
        data = json.loads(msg.payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("le message doit être un objet JSON")
    except (UnicodeDecodeError, ValueError) as error:
        print(f"[MQTT] Message ignoré sur {msg.topic} : {error}")
        return

    try:
        with _lock:
            result = ingest_measurement(data)
        STATE["last_message"] = now()
        STATE["messages"] += 1
        alerts = f" -> ALERTE {', '.join(result['alerts'])}" if result["alerts"] else ""
        print(f"[MQTT] Mesure #{result['id']} enregistrée : {data}{alerts}")
    except Exception as error:  # une mesure invalide ne doit pas arrêter l'écoute
        print(f"[MQTT] Erreur d'enregistrement : {error}")


def start():
    """Démarre l'écoute dans un thread (non bloquant, reconnexion automatique)."""
    global _client
    STATE["enabled"] = True
    _client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        _client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    _client.on_connect = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message = _on_message
    _client.reconnect_delay_set(min_delay=2, max_delay=30)
    print(f"[MQTT] Connexion à {MQTT_BROKER}:{MQTT_PORT}...")
    _client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    _client.loop_start()


def stop():
    if _client is not None:
        _client.loop_stop()
        _client.disconnect()
