"""Importe les données de l'ancienne application (base MySQL « incendie_db »).

Copie dans incendie.db : les comptes (mêmes emails, mêmes mots de passe),
les sites, les appareils, toutes les mesures et toutes les alertes.
Attention : le contenu actuel de incendie.db est remplacé.

À lancer sur le PC où se trouve l'ancienne base (XAMPP / MySQL démarré) :
    pip install mysql-connector-python
    python importer_mysql.py

Paramètres de connexion (facultatifs, sinon valeurs par défaut de XAMPP) :
    python importer_mysql.py --host 127.0.0.1 --port 3306 --user root --password "" --database incendie_db
"""

import argparse
import sys

from database import get_db
from models import init_db


def fetch(cursor, table, columns):
    """Lit une table MySQL ; renvoie [] si la table ou une colonne n'existe pas."""
    cursor.execute(f"SHOW TABLES LIKE '{table}'")
    if not cursor.fetchone():
        print(f"  - table {table} absente, ignorée")
        return []
    cursor.execute(f"SHOW COLUMNS FROM {table}")
    existing = {r["Field"] for r in cursor.fetchall()}
    select = ", ".join(c if c in existing else f"NULL AS {c}" for c in columns)
    cursor.execute(f"SELECT {select} FROM {table} ORDER BY id")
    return cursor.fetchall()


def text(value):
    """Dates MySQL -> texte ISO comme dans la nouvelle base."""
    if value is None:
        return None
    return value.isoformat(timespec="seconds") if hasattr(value, "isoformat") else str(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="incendie_db")
    args = parser.parse_args()

    try:
        import mysql.connector
    except ImportError:
        sys.exit("Installez d'abord le connecteur : pip install mysql-connector-python")

    print(f"Connexion à MySQL {args.host}:{args.port} / {args.database}...")
    try:
        mysql_db = mysql.connector.connect(
            host=args.host, port=args.port, user=args.user,
            password=args.password, database=args.database,
        )
    except mysql.connector.Error as error:
        sys.exit(f"Connexion impossible : {error}\n(XAMPP / MySQL est-il démarré ? Bon port ?)")
    cur = mysql_db.cursor(dictionary=True)

    users = fetch(cur, "users", ["id", "name", "email", "password", "role", "client_id", "status", "created_at"])
    sites = fetch(cur, "sites", ["id", "client_id", "name", "address", "latitude", "longitude"])
    devices = fetch(cur, "devices", ["id", "site_id", "name", "last_seen"])
    measures = fetch(cur, "measurements", ["id", "device_id", "temperature", "humidity", "gaz", "flame_detected", "created_at"])
    alerts = fetch(cur, "alerts", ["id", "device_id", "alert_type", "severity", "message", "temperature",
                                   "humidity", "gaz_value", "flame_detected", "status", "created_at", "resolved_at"])
    mysql_db.close()

    if not users:
        sys.exit("Aucun compte trouvé dans l'ancienne base : import annulé.")

    # Dans l'ancienne base, sites.client_id désigne le client ; on le relie au compte utilisateur.
    def owner(client_id):
        if client_id is None:
            return None
        for u in users:
            if u["client_id"] == client_id:
                return u["id"]
        return client_id if any(u["id"] == client_id for u in users) else None

    init_db()
    with get_db() as db:
        for table in ("sessions", "alerts", "sensor_data", "equipments", "sensors", "devices", "sites", "users"):
            db.execute(f"DELETE FROM {table}")

        db.executemany(
            "INSERT INTO users (id, name, email, password, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(u["id"], u["name"] or u["email"], u["email"].lower(), u["password"],
              u["role"] if u["role"] in ("admin", "client") else "client",
              u["status"] or "active", text(u["created_at"]) or "") for u in users],
        )
        db.executemany(
            "INSERT INTO sites (id, name, address, latitude, longitude, client_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, '')",
            [(s["id"], s["name"], s["address"],
              float(s["latitude"]) if s["latitude"] is not None else None,
              float(s["longitude"]) if s["longitude"] is not None else None,
              owner(s["client_id"])) for s in sites],
        )
        site_ids = {s["id"] for s in sites}
        db.executemany(
            "INSERT INTO devices (id, site_id, name, last_seen) VALUES (?, ?, ?, ?)",
            [(d["id"], d["site_id"] if d["site_id"] in site_ids else None,
              d["name"] or f"ESP32 #{d['id']}", text(d["last_seen"])) for d in devices],
        )
        db.executemany(
            "INSERT INTO sensor_data (id, device_id, temperature, humidity, gas, flame_detected, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(m["id"], m["device_id"], m["temperature"], m["humidity"], m["gaz"],
              int(m["flame_detected"] or 0), text(m["created_at"])) for m in measures],
        )
        db.executemany(
            "INSERT INTO alerts (id, device_id, alert_type, severity, message, temperature, humidity, gas,"
            " flame_detected, status, created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(a["id"], a["device_id"], a["alert_type"] or "fire", a["severity"] or "critical",
              a["message"] or "Alerte incendie", a["temperature"], a["humidity"], a["gaz_value"],
              int(a["flame_detected"] or 0), a["status"] or "active",
              text(a["created_at"]), text(a["resolved_at"])) for a in alerts],
        )
        # Appareils cités par les mesures mais absents de la table devices
        db.execute(
            "INSERT OR IGNORE INTO devices (id, name) SELECT DISTINCT device_id, 'ESP32 #' || device_id FROM sensor_data"
        )

    print(f"Import terminé : {len(users)} compte(s), {len(sites)} site(s), {len(devices)} appareil(s),"
          f" {len(measures)} mesure(s), {len(alerts)} alerte(s).")
    print("Les comptes gardent leurs mots de passe d'origine.")


if __name__ == "__main__":
    main()
