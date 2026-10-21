"""Mesures des capteurs : réception (MQTT ou HTTP), tableau de bord, historique, sites."""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

import mqtt_listener
from config import DEVICE_TIMEOUT_SECONDS, GAS_THRESHOLD, MQTT_BROKER, MQTT_TOPIC
from database import get_db, now, row, rows
from routes.auth import current_user, require_admin

router = APIRouter(prefix="/api", tags=["data"])

DEVICE_KEY = os.getenv("DEVICE_KEY") or None


# ------------------------------------------------------------------
# Lecture du message envoyé par l'ESP32
# ------------------------------------------------------------------

def _first(data, *keys):
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _number(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _flame(value):
    if isinstance(value, bool):
        return int(value)
    return 1 if str(value).strip().lower() in {"1", "true", "on", "detected", "flamme", "oui"} else 0


def ingest_measurement(data):
    """Enregistre une mesure et crée les alertes nécessaires.

    Accepte les noms de champs de l'ESP32 d'origine : temperature, humidity/humidite,
    gaz/gas/gas_value, flamme/flame/flame_detected, device_id.
    Une alerte n'est créée qu'au début d'un épisode (passage de normal à danger),
    pas à chaque message tant que le danger dure.
    """
    try:
        device_id = int(data.get("device_id", 1))
    except (TypeError, ValueError):
        device_id = 1

    temperature = _number(data.get("temperature"))
    humidity = _number(_first(data, "humidity", "humidite"))
    gas = _number(_first(data, "gaz", "gas", "gas_value"))
    flame = _flame(_first(data, "flamme", "flame", "flame_detected") or 0)
    stamp = now()
    created_alerts = []

    with get_db() as db:
        if not db.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone():
            db.execute("INSERT INTO devices (id, name) VALUES (?, ?)", (device_id, f"ESP32 #{device_id}"))

        previous = row(db.execute(
            "SELECT gas, flame_detected FROM sensor_data WHERE device_id = ? ORDER BY id DESC LIMIT 1",
            (device_id,),
        )) or {"gas": None, "flame_detected": 0}

        cur = db.execute(
            "INSERT INTO sensor_data (device_id, temperature, humidity, gas, flame_detected, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (device_id, temperature, humidity, gas, flame, stamp),
        )
        measurement_id = cur.lastrowid
        db.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (stamp, device_id))

        def add_alert(alert_type, severity, message):
            db.execute(
                "INSERT INTO alerts (device_id, alert_type, severity, message, temperature,"
                " humidity, gas, flame_detected, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (device_id, alert_type, severity, message, temperature, humidity, gas, flame, stamp),
            )
            created_alerts.append(alert_type)

        if flame and not previous["flame_detected"]:
            add_alert("fire", "critical", "Flamme détectée par le capteur")

        gas_high = gas is not None and gas > GAS_THRESHOLD
        was_high = previous["gas"] is not None and previous["gas"] > GAS_THRESHOLD
        if gas_high and not was_high:
            add_alert("gas", "warning", f"Niveau de gaz élevé ({gas:g} ppm > {GAS_THRESHOLD:g} ppm)")

    return {"id": measurement_id, "device_id": device_id, "alerts": created_alerts}


# ------------------------------------------------------------------
# Filtre par client : un client ne voit que les appareils de ses sites
# ------------------------------------------------------------------

def visible_devices(db, user):
    """None = tous les appareils (admin), sinon la liste des device_id du client."""
    if user["role"] == "admin":
        return None
    return [r[0] for r in db.execute(
        "SELECT d.id FROM devices d JOIN sites s ON s.id = d.site_id WHERE s.client_id = ?",
        (user["id"],),
    )]


def device_filter(devices, column="device_id"):
    if devices is None:
        return "1 = 1", []
    if not devices:
        return "1 = 0", []
    return f"{column} IN ({','.join('?' * len(devices))})", list(devices)


def is_online(last_seen):
    if not last_seen:
        return False
    return datetime.fromisoformat(last_seen) > datetime.now() - timedelta(seconds=DEVICE_TIMEOUT_SECONDS)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

class MeasurementIn(BaseModel):
    device_id: Optional[int] = 1
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    gaz: Optional[float] = None
    flamme: Optional[int] = 0


@router.post("/data", status_code=201)
def post_data(body: MeasurementIn, x_device_key: Optional[str] = Header(None)):
    """Réception HTTP d'une mesure (alternative à MQTT, utilisée aussi par simulateur.py)."""
    if DEVICE_KEY and x_device_key != DEVICE_KEY:
        raise HTTPException(401, "Clé d'appareil invalide.")
    return {"success": True, **ingest_measurement(body.model_dump())}


@router.get("/data")
def get_data(limit: int = Query(200, ge=1, le=2000), user=Depends(current_user)):
    """Historique des mesures, du plus récent au plus ancien."""
    with get_db() as db:
        where, params = device_filter(visible_devices(db, user))
        data = rows(db.execute(
            f"SELECT * FROM sensor_data WHERE {where} ORDER BY id DESC LIMIT ?", (*params, limit)
        ))
    return {"success": True, "measurements": data, "count": len(data)}


@router.get("/dashboard")
def dashboard(user=Depends(current_user)):
    """Dernière mesure + état global, pour les vues admin et client."""
    with get_db() as db:
        devices = visible_devices(db, user)
        where, params = device_filter(devices)
        measurement = row(db.execute(
            f"SELECT * FROM sensor_data WHERE {where} ORDER BY id DESC LIMIT 1", params
        ))
        active = rows(db.execute(
            f"SELECT * FROM alerts WHERE status = 'active' AND {where} ORDER BY id DESC", params
        ))
        dwhere, dparams = device_filter(devices, "id")
        last_seen = db.execute(f"SELECT MAX(last_seen) FROM devices WHERE {dwhere}", dparams).fetchone()[0]

    flame_now = bool(measurement and measurement["flame_detected"])
    gas_now = bool(measurement and measurement["gas"] is not None and measurement["gas"] > GAS_THRESHOLD)
    if flame_now:
        state = "fire"
    elif gas_now:
        state = "gas"
    elif active:
        state = "alert"
    else:
        state = "ok"

    return {
        "success": True,
        "measurement": measurement,
        "state": state,
        "flame": flame_now,
        "gas_leak": gas_now,
        "gas_threshold": GAS_THRESHOLD,
        "active_alerts": len(active),
        "latest_alert": active[0] if active else None,
        "device_online": is_online(last_seen),
        "has_devices": devices is None or bool(devices),
    }


@router.get("/status")
def status(_user=Depends(current_user)):
    """État des services : serveur, broker MQTT, nœuds ESP32."""
    with get_db() as db:
        devices = rows(db.execute("SELECT id, name, site_id, last_seen FROM devices ORDER BY id"))
    for d in devices:
        d["online"] = is_online(d["last_seen"])
    return {
        "success": True,
        "server": True,
        "mqtt": {**mqtt_listener.STATE, "broker": MQTT_BROKER, "topic": MQTT_TOPIC},
        "devices": devices,
        "devices_online": sum(d["online"] for d in devices),
    }


@router.get("/admin/dashboard")
def admin_dashboard(_admin=Depends(require_admin)):
    with get_db() as db:
        count = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "success": True,
            "active_alerts": count("SELECT COUNT(*) FROM alerts WHERE status = 'active'"),
            "sensors": count("SELECT COUNT(*) FROM sensors"),
            "equipments": count("SELECT COUNT(*) FROM equipments"),
            "users": count("SELECT COUNT(*) FROM users WHERE status = 'active'"),
            "sites": count("SELECT COUNT(*) FROM sites"),
            "devices": count("SELECT COUNT(*) FROM devices"),
            "measurements": count("SELECT COUNT(*) FROM sensor_data"),
        }


# ------------------------------------------------------------------
# Sites surveillés
# ------------------------------------------------------------------

class SiteIn(BaseModel):
    name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    client_id: Optional[int] = None
    device_id: Optional[int] = None


@router.get("/sites")
def get_sites(user=Depends(current_user)):
    with get_db() as db:
        sql = (
            "SELECT s.*, u.name AS client_name FROM sites s"
            " LEFT JOIN users u ON u.id = s.client_id"
        )
        if user["role"] == "admin":
            sites = rows(db.execute(sql + " ORDER BY s.id"))
        else:
            sites = rows(db.execute(sql + " WHERE s.client_id = ? ORDER BY s.id", (user["id"],)))

        for site in sites:
            devices = rows(db.execute(
                "SELECT id, name, last_seen FROM devices WHERE site_id = ?", (site["id"],)
            ))
            ids = [d["id"] for d in devices]
            where, params = device_filter(ids)
            active = [r[0] for r in db.execute(
                f"SELECT alert_type FROM alerts WHERE status = 'active' AND {where}", params
            )]
            online = [d for d in devices if is_online(d["last_seen"])]
            site["devices"] = [{**d, "online": is_online(d["last_seen"])} for d in devices]
            if "fire" in active:
                site["state"] = "fire"
            elif active:
                site["state"] = "alert"
            elif not online:
                site["state"] = "offline"
            else:
                site["state"] = "ok"

    return {"success": True, "sites": sites, "count": len(sites)}


def _attach_device(db, site_id, device_id):
    """Rattache l'ESP32 n° device_id au site (le crée s'il n'a encore rien envoyé)."""
    db.execute("UPDATE devices SET site_id = NULL WHERE site_id = ? AND id != ?", (site_id, device_id or 0))
    if not device_id:
        return
    if db.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone():
        db.execute("UPDATE devices SET site_id = ? WHERE id = ?", (site_id, device_id))
    else:
        db.execute(
            "INSERT INTO devices (id, site_id, name) VALUES (?, ?, ?)",
            (device_id, site_id, f"ESP32 #{device_id}"),
        )


def _check_client(db, client_id):
    if client_id and not db.execute(
        "SELECT 1 FROM users WHERE id = ? AND role = 'client'", (client_id,)
    ).fetchone():
        raise HTTPException(400, "Le client choisi n'existe pas.")


@router.get("/devices")
def get_devices(_admin=Depends(require_admin)):
    with get_db() as db:
        devices = rows(db.execute(
            "SELECT d.*, s.name AS site_name FROM devices d LEFT JOIN sites s ON s.id = d.site_id ORDER BY d.id"
        ))
    for d in devices:
        d["online"] = is_online(d["last_seen"])
    return {"success": True, "devices": devices}


@router.post("/sites", status_code=201)
def create_site(body: SiteIn, _admin=Depends(require_admin)):
    if not body.name.strip():
        raise HTTPException(400, "Le nom du site est obligatoire.")
    with get_db() as db:
        _check_client(db, body.client_id)
        cur = db.execute(
            "INSERT INTO sites (name, address, latitude, longitude, client_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (body.name.strip(), body.address, body.latitude, body.longitude, body.client_id, now()),
        )
        _attach_device(db, cur.lastrowid, body.device_id)
    return {"success": True, "message": "Site ajouté.", "id": cur.lastrowid}


@router.put("/sites/{site_id}")
def update_site(site_id: int, body: SiteIn, _admin=Depends(require_admin)):
    if not body.name.strip():
        raise HTTPException(400, "Le nom du site est obligatoire.")
    with get_db() as db:
        _check_client(db, body.client_id)
        updated = db.execute(
            "UPDATE sites SET name = ?, address = ?, latitude = ?, longitude = ?, client_id = ? WHERE id = ?",
            (body.name.strip(), body.address, body.latitude, body.longitude, body.client_id, site_id),
        ).rowcount
        if not updated:
            raise HTTPException(404, "Site introuvable.")
        _attach_device(db, site_id, body.device_id)
    return {"success": True, "message": "Site modifié."}


@router.delete("/sites/{site_id}")
def delete_site(site_id: int, _admin=Depends(require_admin)):
    with get_db() as db:
        if db.execute("DELETE FROM sites WHERE id = ?", (site_id,)).rowcount == 0:
            raise HTTPException(404, "Site introuvable.")
    return {"success": True, "message": "Site supprimé."}
