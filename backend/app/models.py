from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .config import settings
from .database import Base


def local_now() -> datetime:
    """Heure locale (Europe/Paris), naïve.

    Application mono-utilisateur locale : stockage, comparaisons et affichage
    travaillent tous dans ce même référentiel — ce qu'affichent l'interface et
    les emails est donc directement l'heure du poste.
    """
    return datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)


# Statuts possibles d'une offre. Une offre n'est JAMAIS fermée automatiquement :
# seul l'utilisateur peut passer une offre en "refusee" ou "fermee".
OFFER_STATUSES = [
    "nouvelle",
    "vue",
    "a_postuler",
    "postulee",
    "relancee",
    "entretien",
    "refusee",
    "fermee",
]

# Groupes de statuts partagés par le scan, le digest et les statistiques.
STATUTS_NON_TRAITES = ["nouvelle", "vue", "a_postuler"]  # pas encore de candidature envoyée
STATUTS_EN_ATTENTE = ["postulee", "relancee"]  # candidature envoyée, réponse attendue
STATUTS_CLOS = ["refusee", "fermee"]  # sorties du pipeline (décision de l'utilisateur)

# Libellés affichés (une seule copie côté backend ; le frontend a la sienne dans api.js).
STATUS_LABELS = {
    "nouvelle": "Nouvelle",
    "vue": "Vue",
    "a_postuler": "À postuler",
    "postulee": "Postulée",
    "relancee": "Relancée",
    "entretien": "Entretien",
    "refusee": "Refusée",
    "fermee": "Fermée",
}


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_source_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(200))

    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    contract_type: Mapped[str] = mapped_column(String(60), default="")
    salary_text: Mapped[str] = mapped_column(String(200), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)

    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    still_online: Mapped[bool] = mapped_column(Boolean, default=True)

    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[list] = mapped_column(JSON, default=list)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    final_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    status: Mapped[str] = mapped_column(String(20), default="nouvelle", index=True)
    status_history: Mapped[list] = mapped_column(JSON, default=list)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    interview_prep: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Prochaine action décidée par l'utilisateur (relance, entretien…), datée.
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_action_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Analyse d'écart CV ↔ offre générée par l'IA (compétences manquantes, conseils ATS).
    gap_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Entretiens passés et à venir : [{date, format, interlocuteur, notes}].
    interviews: Mapped[list] = mapped_column(JSON, default=list)

    other_sources: Mapped[list] = mapped_column(JSON, default=list)


class Profile(Base):
    """Profil unique de l'utilisateur (une seule ligne, id=1)."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(120), default="")

    cv_filename: Mapped[str] = mapped_column(String(300), default="")
    cv_text: Mapped[str] = mapped_column(Text, default="")
    cv_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    letter_template: Mapped[str] = mapped_column(Text, default="")

    target_titles: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    location_label: Mapped[str] = mapped_column(String(200), default="Lyon et alentours")
    location_keywords: Mapped[list] = mapped_column(JSON, default=list)
    radius_km: Mapped[int] = mapped_column(Integer, default=40)
    remote_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    contracts: Mapped[list] = mapped_column(JSON, default=list)
    min_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sector_bonus: Mapped[list] = mapped_column(JSON, default=list)
    excluded_keywords: Mapped[list] = mapped_column(JSON, default=list)

    scan_hour: Mapped[str] = mapped_column(String(5), default="07:30")
    sources_enabled: Mapped[dict] = mapped_column(JSON, default=dict)
    # Pondérations du score (voir services/scoring.py DEFAULT_WEIGHTS) ; None = défauts.
    scoring_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Objectif de candidatures envoyées par semaine (jauge du tableau de bord).
    weekly_goal: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    # Requêtes envoyées aux sites d'emploi à chaque scan ; None/vide = défauts des connecteurs.
    search_queries: Mapped[list | None] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, onupdate=local_now)


class Contact(Base):
    """Contact recruteur/RH, rattaché à une entreprise (mini-CRM)."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, onupdate=local_now)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manuel")  # manuel | quotidien
    status: Mapped[str] = mapped_column(String(20), default="en_cours")  # en_cours | termine | erreur
    source_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    seen_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class ActivityLog(Base):
    """Journal des événements de l'application (traçabilité)."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=local_now, index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    message: Mapped[str] = mapped_column(Text)
    offer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), unique=True)  # AAAA-MM-JJ
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
