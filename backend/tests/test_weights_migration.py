"""Tests des pondérations du scoring et de la migration automatique du schéma."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database import Base, ensure_schema
from app.services.cv_parser import extract_skills
from app.services.scoring import DEFAULT_WEIGHTS, score_offer

SEED = json.loads(
    (Path(__file__).resolve().parent.parent / "seed" / "profile_seed.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def profile():
    return {
        "target_titles": SEED["target_titles"],
        "skills": extract_skills(SEED["cv_text"]),
        "location_keywords": SEED["location_keywords"],
        "radius_km": 40,
        "remote_ok": True,
        "contracts": SEED["contracts"],
        "sector_bonus": SEED["sector_bonus"],
        "excluded_keywords": [],
    }


OFFER_LYON = {
    "title": "Test Manager",
    "company": "X",
    "location": "Lyon",
    "contract_type": "CDI",
    "description": "Pilotage QA, management d'équipe, Selenium, Jira, stratégie de test.",
    "remote": False,
}
OFFER_PARIS = dict(OFFER_LYON, location="Paris")


def test_poids_par_defaut_inchanges(profile):
    """Sans pondérations personnalisées, le comportement historique est conservé."""
    without = score_offer(OFFER_LYON, profile).score
    with_defaults = score_offer(OFFER_LYON, dict(profile, scoring_weights=dict(DEFAULT_WEIGHTS))).score
    assert without == with_defaults


def test_poids_localisation_augmente_l_ecart(profile):
    """Monter le poids de la localisation creuse l'écart Lyon vs Paris."""
    base_gap = score_offer(OFFER_LYON, profile).score - score_offer(OFFER_PARIS, profile).score
    heavy = dict(profile, scoring_weights={**DEFAULT_WEIGHTS, "localisation": 45})
    heavy_gap = score_offer(OFFER_LYON, heavy).score - score_offer(OFFER_PARIS, heavy).score
    assert heavy_gap > base_gap


def test_poids_a_zero_neutralise_le_critere(profile):
    zero_loc = dict(profile, scoring_weights={**DEFAULT_WEIGHTS, "localisation": 0})
    assert score_offer(OFFER_LYON, zero_loc).score == score_offer(OFFER_PARIS, zero_loc).score


def test_total_libre_ramene_sur_100(profile):
    """Des pondérations doublées donnent le même score sur 100."""
    doubled = dict(profile, scoring_weights={k: v * 2 for k, v in DEFAULT_WEIGHTS.items()})
    assert score_offer(OFFER_LYON, doubled).score == pytest.approx(
        score_offer(OFFER_LYON, profile).score, abs=0.2
    )


def test_migration_ajoute_les_colonnes(tmp_path):
    """Une base d'une version antérieure (colonnes manquantes) est migrée sans perte."""
    db_path = tmp_path / "ancienne.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # Simule une base V1 : table offers sans les colonnes récentes.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE offers (id INTEGER PRIMARY KEY, fingerprint VARCHAR, source VARCHAR, "
            "source_id VARCHAR, title VARCHAR, company VARCHAR, location VARCHAR, description TEXT, "
            "url TEXT, contract_type VARCHAR, salary_text VARCHAR, remote BOOLEAN, published_at DATETIME, "
            "collected_at DATETIME, last_seen_at DATETIME, still_online BOOLEAN, score FLOAT, "
            "score_breakdown JSON, ai_score FLOAT, ai_reason TEXT, final_score FLOAT, status VARCHAR, "
            "status_history JSON, favorite BOOLEAN, notes TEXT, cover_letter TEXT, other_sources JSON)"
        ))
        conn.execute(text(
            "INSERT INTO offers (fingerprint, source, source_id, title, status, final_score) "
            "VALUES ('fp1', 'test', '1', 'Test Manager', 'postulee', 90)"
        ))

    ensure_schema(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("offers")}
    assert "interview_prep" in columns
    with engine.connect() as conn:
        row = conn.execute(text("SELECT title, status, interview_prep FROM offers")).fetchone()
    assert row[0] == "Test Manager" and row[1] == "postulee"  # données préservées
    assert row[2] is None
    # La table profile (absente) a aussi été créée avec la colonne des pondérations.
    assert "scoring_weights" in {c["name"] for c in inspect(engine).get_columns("profile")}
