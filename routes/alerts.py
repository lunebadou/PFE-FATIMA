"""Alertes incendie : liste et résolution par l'administrateur."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db, now, row, rows
from routes.auth import current_user, require_admin
from routes.data import device_filter, visible_devices

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def get_alerts(
    status: Optional[str] = Query(None, pattern="^(active|resolved)$"),
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(current_user),
):
    with get_db() as db:
        where, params = device_filter(visible_devices(db, user), "a.device_id")
        if status:
            where += " AND a.status = ?"
            params.append(status)
        alerts = rows(db.execute(
            "SELECT a.*, d.name AS device_name, s.name AS site_name, u.name AS resolved_by_name"
            " FROM alerts a"
            " LEFT JOIN devices d ON d.id = a.device_id"
            " LEFT JOIN sites s ON s.id = d.site_id"
            " LEFT JOIN users u ON u.id = a.resolved_by"
            f" WHERE {where} ORDER BY a.id DESC LIMIT ?",
            (*params, limit),
        ))
    return {"success": True, "alerts": alerts, "count": len(alerts)}


@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int, admin=Depends(require_admin)):
    with get_db() as db:
        alert = row(db.execute("SELECT status FROM alerts WHERE id = ?", (alert_id,)))
        if not alert:
            raise HTTPException(404, "Alerte introuvable.")
        if alert["status"] != "active":
            raise HTTPException(400, "Cette alerte est déjà résolue.")
        db.execute(
            "UPDATE alerts SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE id = ?",
            (now(), admin["id"], alert_id),
        )
    return {"success": True, "message": "Alerte résolue."}


@router.put("/resolve-all")
def resolve_all(admin=Depends(require_admin)):
    with get_db() as db:
        count = db.execute(
            "UPDATE alerts SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE status = 'active'",
            (now(), admin["id"]),
        ).rowcount
    return {"success": True, "message": f"{count} alerte(s) résolue(s).", "count": count}
