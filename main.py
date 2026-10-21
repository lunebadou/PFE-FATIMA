"""TIMDEIZ Incendie — point d'entrée.

Lance en une seule commande :
  - l'API FastAPI (/api/...)
  - l'interface web (dossier frontend/)
  - l'écoute MQTT des mesures de l'ESP32 (en arrière-plan)

Utilisation :  python main.py
"""

import socket
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import mqtt_listener
from config import HOST, MQTT_ENABLED, PORT
from models import init_db
from routes import alerts, auth, data

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


@asynccontextmanager
async def lifespan(app):
    init_db()
    if MQTT_ENABLED:
        mqtt_listener.start()
    else:
        print("[MQTT] Désactivé (MQTT_ENABLED=0)")
    yield
    mqtt_listener.stop()


app = FastAPI(title="TIMDEIZ Incendie", version="2.0", lifespan=lifespan)

# Autorise aussi l'interface ouverte depuis une autre adresse (ex : Live Server)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(data.router)
app.include_router(alerts.router)


@app.get("/api/test")
def test():
    return {"success": True, "message": "API TIMDEIZ Incendie opérationnelle."}


# L'interface web est servie à la racine : http://<ip>:5000/
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


def local_ip():
    """Adresse IP du PC sur le réseau Wi-Fi (pour l'ouvrir depuis un téléphone)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    ip = local_ip()
    print()
    print("=" * 60)
    print("  TIMDEIZ INCENDIE")
    print(f"  Sur ce PC        : http://localhost:{PORT}")
    print(f"  Sur le téléphone : http://{ip}:{PORT}   (même Wi-Fi)")
    print(f"  Documentation API: http://localhost:{PORT}/docs")
    print("=" * 60)
    print()
    uvicorn.run(app, host=HOST, port=PORT)
