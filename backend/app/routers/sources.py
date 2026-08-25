from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..connectors import ALL_CONNECTORS
from ..database import get_db
from ..models import Profile, ScanRun
from ..services import scheduler
from ..services.claude_ai import cli_available
from ..services.emailer import smtp_configured

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources(db: Session = Depends(get_db)):
    """État de chaque source : configurée ? activée ? statistiques du dernier scan."""
    profile = db.get(Profile, 1)
    enabled = (profile.sources_enabled or {}) if profile else {}
    from datetime import timedelta

    from ..models import local_now

    # Fenêtre de 14 jours (bornée à 60 scans pour rester lisible).
    runs = (
        db.query(ScanRun)
        .filter(ScanRun.status == "termine", ScanRun.started_at >= local_now() - timedelta(days=14))
        .order_by(ScanRun.id.desc())
        .limit(60)
        .all()
    )
    stats = runs[0].source_stats if runs else {}

    def history(name: str) -> list[dict]:
        """Ok/erreur de la source sur les derniers scans (du plus ancien au plus récent)."""
        entries = []
        for run in reversed(runs):
            source_stat = (run.source_stats or {}).get(name)
            if not source_stat or source_stat.get("skipped"):
                continue
            entries.append({
                "date": run.started_at.strftime("%d/%m %H:%M"),
                "ok": not source_stat.get("errors"),
                "new": source_stat.get("new", 0),
            })
        return entries

    return {
        "sources": [
            {
                "name": c.name,
                "label": c.label,
                "needs_key": c.needs_key,
                "configured": c.is_configured(),
                "enabled": enabled.get(c.name, True),
                "last_stats": stats.get(c.name),
                "history": history(c.name),
            }
            for c in ALL_CONNECTORS
        ],
        "ai": {
            "available": cli_available(),
            "detail": "Session locale Claude Code (CLI « claude »)" if cli_available()
            else "CLI « claude » introuvable sur ce poste — scoring par règles uniquement",
        },
        "email": {
            "configured": smtp_configured(),
        },
        "next_daily_scan": scheduler.next_run_time(),
    }
