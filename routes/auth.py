"""Connexion, inscription, profil et contrôle des rôles."""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config import SESSION_HOURS
from database import get_db, now, row
from models import check_password, hash_password, needs_setup

router = APIRouter(prefix="/api", tags=["auth"])

USER_FIELDS = "id, name, email, role, phone, status, created_at"


# ------------------------------------------------------------------
# Dépendances : utilisateur connecté / administrateur
# ------------------------------------------------------------------

def current_user(authorization: Optional[str] = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Veuillez vous connecter.")

    with get_db() as db:
        user = row(db.execute(
            "SELECT u.id, u.name, u.email, u.role, u.phone, u.status, u.created_at,"
            " s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        ))
        if not user or user["expires_at"] < now():
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            raise HTTPException(401, "Session expirée, veuillez vous reconnecter.")

    user.pop("expires_at")
    user["token"] = token
    return user


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Accès réservé à l'administrateur.")
    return user


# ------------------------------------------------------------------
# Schémas des requêtes
# ------------------------------------------------------------------

class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    phone: Optional[str] = None


class ProfileIn(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "client"
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None


def _clean_email(email):
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Adresse email invalide.")
    return email


def _check_password_length(password):
    if len(password) < 6:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 6 caractères.")


def _create_user(db, name, email, password, role, phone=None):
    name = name.strip()
    email = _clean_email(email)
    if not name:
        raise HTTPException(400, "Le nom est obligatoire.")
    if role not in ("admin", "client"):
        raise HTTPException(400, "Rôle invalide.")
    _check_password_length(password)
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise HTTPException(409, "Un compte existe déjà avec cet email.")
    cur = db.execute(
        "INSERT INTO users (name, email, password, role, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, email, hash_password(password), role, (phone or "").strip() or None, now()),
    )
    return row(db.execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (cur.lastrowid,)))


def _open_session(db, user):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    db.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user["id"], expires),
    )
    return token


# ------------------------------------------------------------------
# Premier lancement : création du compte administrateur
# ------------------------------------------------------------------

@router.get("/setup")
def setup_status():
    return {"success": True, "needs_setup": needs_setup()}


@router.post("/setup", status_code=201)
def setup(body: RegisterIn):
    if not needs_setup():
        raise HTTPException(403, "L'application est déjà configurée.")
    with get_db() as db:
        user = _create_user(db, body.name, body.email, body.password, "admin", body.phone)
        token = _open_session(db, user)
    return {"success": True, "message": "Compte administrateur créé.", "token": token, "user": user}


# ------------------------------------------------------------------
# Connexion / inscription
# ------------------------------------------------------------------

@router.post("/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    with get_db() as db:
        user = row(db.execute(
            f"SELECT {USER_FIELDS}, password FROM users WHERE email = ?", (email,)
        ))
        if not user or not check_password(body.password, user.pop("password")):
            raise HTTPException(401, "Email ou mot de passe incorrect.")
        if user["status"] != "active":
            raise HTTPException(403, "Ce compte est désactivé. Contactez l'administrateur.")
        token = _open_session(db, user)

    return {"success": True, "message": "Connexion réussie.", "token": token, "user": user}


@router.post("/register", status_code=201)
def register(body: RegisterIn):
    with get_db() as db:
        # Les inscriptions publiques créent toujours un compte client
        _create_user(db, body.name, body.email, body.password, "client", body.phone)
    return {"success": True, "message": "Compte créé. Vous pouvez vous connecter."}


@router.post("/logout")
def logout(user=Depends(current_user)):
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE token = ?", (user["token"],))
    return {"success": True}


@router.get("/profile")
def get_profile(user=Depends(current_user)):
    user = dict(user)
    user.pop("token")
    return {"success": True, "user": user}


@router.put("/profile")
def update_profile(body: ProfileIn, user=Depends(current_user)):
    name = body.name.strip()
    email = _clean_email(body.email)
    if not name:
        raise HTTPException(400, "Le nom est obligatoire.")

    with get_db() as db:
        taken = db.execute(
            "SELECT 1 FROM users WHERE email = ? AND id != ?", (email, user["id"])
        ).fetchone()
        if taken:
            raise HTTPException(409, "Cet email est déjà utilisé par un autre compte.")
        db.execute(
            "UPDATE users SET name = ?, email = ?, phone = ? WHERE id = ?",
            (name, email, (body.phone or "").strip() or None, user["id"]),
        )
        updated = row(db.execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user["id"],)))

    return {"success": True, "message": "Profil mis à jour.", "user": updated}


@router.put("/change-password")
def change_password(body: PasswordIn, user=Depends(current_user)):
    _check_password_length(body.new_password)

    with get_db() as db:
        hashed = db.execute("SELECT password FROM users WHERE id = ?", (user["id"],)).fetchone()[0]
        if not check_password(body.current_password, hashed):
            raise HTTPException(400, "Mot de passe actuel incorrect.")
        db.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(body.new_password), user["id"]),
        )

    return {"success": True, "message": "Mot de passe modifié."}


# ------------------------------------------------------------------
# Gestion des utilisateurs (administrateur)
# ------------------------------------------------------------------

@router.get("/users")
def list_users(_admin=Depends(require_admin)):
    with get_db() as db:
        users = [dict(r) for r in db.execute(
            f"SELECT {USER_FIELDS}, (SELECT COUNT(*) FROM sites WHERE client_id = users.id) AS sites"
            " FROM users ORDER BY id"
        )]
    return {"success": True, "users": users}


@router.post("/users", status_code=201)
def create_user(body: UserIn, _admin=Depends(require_admin)):
    with get_db() as db:
        user = _create_user(db, body.name, body.email, body.password, body.role, body.phone)
    return {"success": True, "message": "Utilisateur créé.", "user": user}


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin=Depends(require_admin)):
    with get_db() as db:
        user = row(db.execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,)))
        if not user:
            raise HTTPException(404, "Utilisateur introuvable.")
        if user_id == admin["id"] and (
            (body.role and body.role != "admin") or (body.status and body.status != "active")
        ):
            raise HTTPException(400, "Vous ne pouvez pas retirer vos propres droits d'administrateur.")
        if body.role is not None and body.role not in ("admin", "client"):
            raise HTTPException(400, "Rôle invalide.")
        if body.status is not None and body.status not in ("active", "disabled"):
            raise HTTPException(400, "Statut invalide.")

        changes = {}
        if body.name is not None and body.name.strip():
            changes["name"] = body.name.strip()
        if body.phone is not None:
            changes["phone"] = body.phone.strip() or None
        if body.role is not None:
            changes["role"] = body.role
        if body.status is not None:
            changes["status"] = body.status
        if body.password:
            _check_password_length(body.password)
            changes["password"] = hash_password(body.password)

        if changes:
            db.execute(
                f"UPDATE users SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                (*changes.values(), user_id),
            )
        if body.status == "disabled" or body.password:
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        user = row(db.execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,)))
    return {"success": True, "message": "Utilisateur mis à jour.", "user": user}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "Vous ne pouvez pas supprimer votre propre compte.")
    with get_db() as db:
        if db.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount == 0:
            raise HTTPException(404, "Utilisateur introuvable.")
    return {"success": True, "message": "Utilisateur supprimé."}
