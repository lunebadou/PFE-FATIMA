# TIMDEIZ Incendie

Plateforme de supervision du réseau de capteurs Wi-Fi pour la détection et l'alerte incendie
(mémoire de master de Fatoumata DIALLO, ESMT).

Un ESP32 (DHT22, MQ-2, capteur de flamme) publie ses mesures sur un broker MQTT.
Cette application les reçoit, les enregistre, déclenche les alertes et les affiche
dans une interface web utilisable sur PC et sur téléphone.

```
ESP32 ──MQTT──► broker 209.38.68.161:1883 (topic incendie/data)
                        │
                        ▼
        main.py  (un seul programme)
        ├── écoute MQTT en arrière-plan
        ├── base SQLite  (fichier incendie.db, créé tout seul)
        ├── API FastAPI  (/api/...)
        └── interface web (dossier frontend/)
                        │
                        ▼
        navigateur PC ou téléphone : http://<ip-du-pc>:5000
```

## Lancer l'application (Windows)

1. Installer Python 3.10 ou plus récent depuis https://www.python.org/downloads/
   en cochant **« Add python.exe to PATH »**.
2. Double-cliquer sur **`start.bat`**.

La première fois, il installe ce qu'il faut (environ une minute), puis le navigateur s'ouvre.
La fenêtre noire affiche aussi l'adresse à taper sur le téléphone. **Ne pas fermer cette fenêtre** :
la fermer arrête l'application.

Sans `start.bat` (Mac, Linux, ou à la main) :

```bash
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux : source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Premier lancement

La base démarre vide. La page d'accueil propose de **créer le compte administrateur**.
Ensuite, depuis l'espace administrateur :

1. **Utilisateurs** → « Ajouter un utilisateur » : créer les comptes clients (ou d'autres admins).
2. **Sites** → « Ajouter un site » : nom, adresse, coordonnées GPS, le client rattaché
   et le n° de l'ESP32 installé (`device_id`, **1** par défaut dans le code Arduino).

Dès que l'ESP32 envoie des mesures, elles apparaissent sur le tableau de bord.
Un client peut aussi créer lui-même son compte (« Créer un compte ») ; l'administrateur
le rattache ensuite à son site.

## Les deux rôles

| | Administrateur | Client |
|---|---|---|
| Mesures en direct, graphique | tous les sites | son site uniquement |
| Alertes | toutes, peut les **résoudre** | celles de son site (lecture) |
| Historique des mesures | tout, export CSV | son site |
| Sites | créer, modifier, supprimer | voit le sien |
| Utilisateurs | créer, modifier, désactiver, supprimer, changer un mot de passe | — |
| Profil et mot de passe, paramètres | oui | oui |

## Utiliser depuis un téléphone

Le téléphone doit être sur **le même Wi-Fi** que le PC. Taper l'adresse affichée par
`start.bat` (par exemple `http://192.168.1.25:5000`).

Si la page ne s'ouvre pas, c'est le pare-feu Windows qui bloque. Le plus simple : au premier lancement,
Windows demande « Autoriser l'accès » pour Python, cliquer **Autoriser** (cocher « Réseaux privés »).
Sinon, dans un invite de commandes **lancé en administrateur** :

```
netsh advfirewall firewall add rule name="TIMDEIZ Incendie" dir=in action=allow protocol=TCP localport=5000
```

L'adresse de l'API dans le JavaScript n'est pas écrite en dur : elle suit automatiquement
l'adresse tapée dans le navigateur (`window.location.hostname`).

## Données envoyées par l'ESP32

Message JSON publié sur le topic `incendie/data` :

```json
{"device_id": 1, "temperature": 27.0, "humidity": 57.8, "gaz": 43, "flamme": 0}
```

Les noms de l'ancien code sont acceptés (`humidite`, `gas`, `gas_value`, `flame`,
`flame_detected`, `flamme` = `0/1`, `true/false`, `"detected"`...).

L'ESP32 peut aussi envoyer en HTTP : `POST http://<ip-du-pc>:5000/api/data` avec le même JSON.

### Règles d'alerte

- **Incendie (critique)** : la flamme passe de 0 à 1.
- **Fuite de gaz (avertissement)** : le gaz dépasse le seuil (300 ppm par défaut, `GAS_THRESHOLD`).

Une seule alerte est créée par épisode (pas une par message tant que le danger dure).
Elle reste active jusqu'à ce que l'administrateur la résolve.
Un ESP32 qui n'a rien envoyé depuis 60 s est affiché « hors ligne ».

## Tester sans l'ESP32

Avec l'application lancée, dans une autre fenêtre :

```bash
.venv\Scripts\python simulateur.py          # mesures en continu, avec feu et fuite de gaz de temps en temps
.venv\Scripts\python simulateur.py --feu    # une détection de flamme immédiate
```

Le simulateur envoie pour l'ESP32 n° 1 : rattachez-le d'abord à un site pour qu'un client le voie.

## Configuration (facultatif)

Copier `.env.example` en `.env` (fait automatiquement par `start.bat`) et modifier si besoin :
broker MQTT et identifiants, port, seuil de gaz, délai « hors ligne ».
Le fichier `.env` contient des identifiants : il n'est pas envoyé sur GitHub (voir `.gitignore`).

## Récupérer l'ancienne base MySQL (facultatif)

Si l'ancienne application (Flask + MySQL/XAMPP) est encore installée sur un PC,
ce script copie ses comptes (mêmes mots de passe), sites, mesures et alertes :

```bash
.venv\Scripts\pip install mysql-connector-python
.venv\Scripts\python importer_mysql.py --port 3306 --user root --password ""
```

Attention : il remplace le contenu de la nouvelle base.

## Fichiers

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée : lance l'API, l'interface et l'écoute MQTT |
| `config.py` | Réglages (lus dans `.env`) |
| `database.py` | Connexion SQLite |
| `models.py` | Tables, mots de passe (bcrypt) |
| `mqtt_listener.py` | Réception des messages de l'ESP32 |
| `routes/auth.py` | Premier lancement, connexion, inscription, profil, utilisateurs |
| `routes/data.py` | Réception des mesures, tableau de bord, historique, sites |
| `routes/alerts.py` | Liste et résolution des alertes |
| `frontend/` | Pages web : connexion, administrateur, client |
| `simulateur.py` | Faux ESP32 pour les tests |
| `importer_mysql.py` | Import de l'ancienne base MySQL |
| `start.bat` | Lancement en double-clic sous Windows |

La documentation interactive de l'API est disponible sur `http://localhost:5000/docs`.
