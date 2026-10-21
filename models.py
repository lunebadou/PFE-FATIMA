"""Schéma de la base et données de départ."""

import hashlib
import hmac

import bcrypt

from database import get_db

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,              -- empreinte bcrypt
    role        TEXT NOT NULL DEFAULT 'client' CHECK (role IN ('admin', 'client')),
    phone       TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    address     TEXT,
    latitude    REAL,
    longitude   REAL,
    client_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL
);

-- Nœuds ESP32 : chaque message MQTT porte un device_id
CREATE TABLE IF NOT EXISTS devices (
    id          INTEGER PRIMARY KEY,
    site_id     INTEGER REFERENCES sites(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    last_seen   TEXT
);

-- Inventaire matériel affiché dans le tableau de bord
CREATE TABLE IF NOT EXISTS sensors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    role        TEXT
);

CREATE TABLE IF NOT EXISTS sensor_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER NOT NULL,
    temperature     REAL,
    humidity        REAL,
    gas             REAL,
    flame_detected  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sensor_data_device ON sensor_data (device_id, id);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER NOT NULL,
    alert_type      TEXT NOT NULL,          -- 'fire' ou 'gas'
    severity        TEXT NOT NULL,          -- 'critical' ou 'warning'
    message         TEXT NOT NULL,
    temperature     REAL,
    humidity        REAL,
    gas             REAL,
    flame_detected  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',   -- 'active' ou 'resolved'
    created_at      TEXT NOT NULL,
    resolved_at     TEXT,
    resolved_by     INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);
"""


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, hashed):
    """Vérifie un mot de passe bcrypt, ou une empreinte Werkzeug importée de l'ancienne appli Flask."""
    if hashed.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False
    return _check_werkzeug_hash(password, hashed)


def _check_werkzeug_hash(password, hashed):
    # Format Werkzeug : "scrypt:n:r:p$sel$empreinte" ou "pbkdf2:sha256:iterations$sel$empreinte"
    try:
        method, salt, expected = hashed.split("$", 2)
        parts = method.split(":")
        pw, salt_b = password.encode("utf-8"), salt.encode("utf-8")
        if parts[0] == "scrypt":
            n, r, p = (int(x) for x in parts[1:4]) if len(parts) == 4 else (2 ** 15, 8, 1)
            digest = hashlib.scrypt(pw, salt=salt_b, n=n, r=r, p=p, maxmem=132 * n * r * p, dklen=64)
        elif parts[0] == "pbkdf2":
            name = parts[1] if len(parts) > 1 else "sha256"
            iterations = int(parts[2]) if len(parts) > 2 else 600000
            digest = hashlib.pbkdf2_hmac(name, pw, salt_b, iterations)
        else:
            return False
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def init_db():
    """Crée les tables. La base démarre vide : le premier compte administrateur
    est créé depuis la page de connexion (premier lancement)."""
    with get_db() as db:
        db.executescript(SCHEMA)

        if db.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 0:
            # Le nœud de la maquette : l'ESP32 envoie device_id = 1 par défaut.
            # Il sera rattaché à un site depuis la page « Sites ».
            db.execute("INSERT INTO devices (id, name) VALUES (1, 'ESP32-SIM800L principal')")
            db.executemany(
                "INSERT INTO sensors (device_id, name, type) VALUES (1, ?, ?)",
                [
                    ("DHT22", "Température / humidité"),
                    ("MQ-2", "Gaz / fumée"),
                    ("Capteur de flamme IR", "Flamme"),
                ],
            )
            db.executemany(
                "INSERT INTO equipments (device_id, name, role) VALUES (1, ?, ?)",
                [
                    ("Buzzer", "Alarme sonore"),
                    ("Relais + mini-pompe", "Extinction automatique"),
                    ("Écran LCD I2C", "Affichage local"),
                    ("Module SIM800L", "Secours GSM et SMS"),
                ],
            )


def needs_setup():
    """Vrai tant qu'aucun administrateur n'existe."""
    with get_db() as db:
        return db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] == 0
