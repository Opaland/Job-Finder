from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
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

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manuel")  # manuel | quotidien
    status: Mapped[str] = mapped_column(String(20), default="en_cours")  # en_cours | termine | erreur
    source_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    seen_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), unique=True)  # AAAA-MM-JJ
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
