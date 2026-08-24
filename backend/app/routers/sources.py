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
    last_run = db.query(ScanRun).filter(ScanRun.status == "termine").order_by(ScanRun.id.desc()).first()
    stats = last_run.source_stats if last_run else {}

    return {
        "sources": [
            {
                "name": c.name,
                "label": c.label,
                "needs_key": c.needs_key,
                "configured": c.is_configured(),
                "enabled": enabled.get(c.name, True),
                "last_stats": stats.get(c.name),
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
