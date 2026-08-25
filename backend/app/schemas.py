"""Schémas Pydantic de l'API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class OfferSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    title: str
    company: str
    location: str
    contract_type: str
    salary_text: str
    remote: bool
    url: str
    published_at: datetime | None
    collected_at: datetime
    still_online: bool
    score: float
    ai_score: float | None
    final_score: float
    status: str
    favorite: bool
    next_action_date: datetime | None = None


class OfferDetail(OfferSummary):
    description: str
    score_breakdown: list
    ai_reason: str
    notes: str
    cover_letter: str
    interview_prep: str | None
    gap_analysis: str | None
    next_action_note: str | None
    other_sources: list
    interviews: list
    status_history: list
    last_seen_at: datetime


class InterviewIn(BaseModel):
    """Entretien planifié ou passé, rattaché à une offre."""

    date: datetime
    format: str = ""          # visio, téléphone, sur site…
    interlocuteur: str = ""
    notes: str = ""


class InterviewReport(BaseModel):
    """Compte-rendu rempli après l'entretien."""

    compte_rendu: str | None = None
    ressenti: str | None = None       # bon, mitige, mauvais
    suite: str | None = None          # ce que le recruteur a annoncé
    relance_le: datetime | None = None  # cale la prochaine action sur cette date


class ManualOffer(BaseModel):
    """Offre ajoutée à la main (annonce collée)."""

    url: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    raw_text: str | None = None


class OfferUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    favorite: bool | None = None
    cover_letter: str | None = None
    interview_prep: str | None = None
    # None explicite = effacer l'action (distingué de « non fourni » via model_fields_set).
    next_action_date: datetime | None = None
    next_action_note: str | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    email: str
    cv_filename: str
    cv_text: str
    cv_updated_at: datetime | None
    letter_template: str
    target_titles: list
    skills: list
    location_label: str
    location_keywords: list
    radius_km: int
    remote_ok: bool
    contracts: list
    min_salary: int | None
    sector_bonus: list
    excluded_keywords: list
    scan_hour: str
    sources_enabled: dict
    scoring_weights: dict | None
    weekly_goal: int
    search_queries: list | None


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    letter_template: str | None = None
    target_titles: list | None = None
    skills: list | None = None
    location_label: str | None = None
    location_keywords: list | None = None
    radius_km: int | None = None
    remote_ok: bool | None = None
    contracts: list | None = None
    min_salary: int | None = None
    sector_bonus: list | None = None
    excluded_keywords: list | None = None
    scan_hour: str | None = None
    sources_enabled: dict | None = None
    scoring_weights: dict[str, float] | None = None
    weekly_goal: int | None = None
    search_queries: list[str] | None = None

    @field_validator("scoring_weights")
    @classmethod
    def _poids_positifs(cls, value):
        if value is None:
            return None
        return {k: max(0.0, v) for k, v in value.items()}


class ScanRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    trigger: str
    status: str
    source_stats: dict
    new_count: int
    seen_count: int
    error_count: int


class DigestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: str
    created_at: datetime
    payload: dict
    email_sent: bool
