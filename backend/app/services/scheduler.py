"""Scan quotidien automatique (APScheduler), à l'heure choisie dans le profil.

Le scan tourne tant que l'application est lancée. Pour un scan sans interface,
`python -m app.cli scan` peut aussi être planifié via le Planificateur de
tâches Windows (voir README).
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import settings
from ..database import SessionLocal
from ..models import Profile

logger = logging.getLogger("jobfinder.scheduler")

_scheduler: BackgroundScheduler | None = None
JOB_ID = "scan_quotidien"


def _daily_job():
    from .digest import build_digest, send_digest_email
    from .scan import run_scan

    db = SessionLocal()
    try:
        logger.info("Scan quotidien : démarrage")
        run_scan(db, trigger="quotidien")
        digest = build_digest(db)
        sent = send_digest_email(db, digest)
        logger.info("Scan quotidien terminé (email envoyé : %s)", sent)
    except RuntimeError as exc:
        logger.warning("Scan quotidien ignoré : %s", exc)
    except Exception:  # noqa: BLE001
        logger.exception("Scan quotidien en erreur")
    finally:
        db.close()


def _parse_hour(value: str) -> tuple[int, int]:
    try:
        hour_s, minute_s = value.strip().split(":")
        hour, minute = int(hour_s), int(minute_s)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    return 7, 30


def start_scheduler():
    global _scheduler
    db = SessionLocal()
    try:
        profile = db.get(Profile, 1)
        scan_hour = profile.scan_hour if profile else settings.scan_hour
    finally:
        db.close()

    hour, minute = _parse_hour(scan_hour or settings.scan_hour)
    _scheduler = BackgroundScheduler(timezone=ZoneInfo(settings.timezone))
    _scheduler.add_job(
        _daily_job,
        CronTrigger(hour=hour, minute=minute),
        id=JOB_ID,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scan quotidien programmé à %02d:%02d (%s)", hour, minute, settings.timezone)


def reschedule(scan_hour: str):
    """Reprogramme le scan quotidien (après changement de l'heure dans le profil)."""
    if _scheduler is None:
        return
    hour, minute = _parse_hour(scan_hour)
    _scheduler.add_job(
        _daily_job,
        CronTrigger(hour=hour, minute=minute),
        id=JOB_ID,
        replace_existing=True,
    )
    logger.info("Scan quotidien reprogrammé à %02d:%02d", hour, minute)


def next_run_time() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
