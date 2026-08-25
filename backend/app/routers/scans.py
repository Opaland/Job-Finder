import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import ScanRun
from ..schemas import ScanRunOut
from ..services.journal import log_event
from ..services.scan import run_full_scan, scan_status
from ..services.verrou import MESSAGE_SCAN_AILLEURS, verrou_disponible

logger = logging.getLogger("jobfinder.api")
router = APIRouter(prefix="/api/scans", tags=["scans"])


def _scan_thread():
    db = SessionLocal()
    try:
        # Pas d'email pour un scan lancé à la main : l'utilisateur est devant l'appli.
        run_full_scan(db, trigger="manuel", send_email=False)
    except RuntimeError as exc:
        # Scan déjà en cours ailleurs : le thread ne peut plus répondre à
        # l'utilisateur, le journal garde la trace de ce qui s'est passé.
        log_event(db, "scan", f"Scan manuel non lancé : {exc}")
    except Exception:  # noqa: BLE001
        logger.exception("Scan manuel en erreur")
    finally:
        db.close()


@router.post("")
def start_scan():
    """Lance un scan manuel en arrière-plan."""
    if scan_status().get("running"):
        raise HTTPException(409, "Un scan est déjà en cours")
    if not verrou_disponible():
        raise HTTPException(409, MESSAGE_SCAN_AILLEURS)
    threading.Thread(target=_scan_thread, daemon=True).start()
    return {"started": True}


@router.get("/status")
def get_status():
    return scan_status()


@router.get("", response_model=list[ScanRunOut])
def list_scans(limit: int = 20, db: Session = Depends(get_db)):
    return db.query(ScanRun).order_by(ScanRun.id.desc()).limit(min(limit, 100)).all()
