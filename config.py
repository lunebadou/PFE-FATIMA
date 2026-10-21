"""Configuration de l'application, lue depuis le fichier .env (facultatif)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Serveur web (API + interface)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))

# Base de données SQLite (un simple fichier, créé automatiquement)
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "incendie.db"))

# Broker MQTT où l'ESP32 publie ses mesures
MQTT_ENABLED = os.getenv("MQTT_ENABLED", "1") == "1"
MQTT_BROKER = os.getenv("MQTT_BROKER", "209.38.68.161")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "incendie/data")

# Seuil de gaz (ppm) au-delà duquel une alerte "fuite de gaz" est créée
GAS_THRESHOLD = float(os.getenv("GAS_THRESHOLD", "300"))

# Un appareil est considéré hors ligne s'il n'a rien envoyé depuis ce délai
DEVICE_TIMEOUT_SECONDS = int(os.getenv("DEVICE_TIMEOUT_SECONDS", "60"))

# Durée de validité d'une session de connexion
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "24"))
