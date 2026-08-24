"""Tests du moteur de classement : les offres proches du CV de Cédric doivent scorer haut."""
import json
from pathlib import Path

import pytest

from app.services.cv_parser import extract_skills
from app.services.scoring import combined_score, score_offer

SEED = json.loads(
    (Path(__file__).resolve().parent.parent / "seed" / "profile_seed.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def profile():
    return {
        "target_titles": SEED["target_titles"],
        "skills": extract_skills(SEED["cv_text"]),
        "location_keywords": SEED["location_keywords"],
        "radius_km": SEED["radius_km"],
        "remote_ok": True,
        "contracts": SEED["contracts"],
        "sector_bonus": SEED["sector_bonus"],
        "excluded_keywords": [],
    }


def test_offre_ideale_score_tres_haut(profile):
    """Test Manager santé à Lyon en CDI = le poste qu'il occupe déjà → score très élevé."""
    offer = {
        "title": "Test Manager / QA Lead",
        "company": "Éditeur santé",
        "location": "Lyon (69)",
        "contract_type": "CDI",
        "description": (
            "Éditeur de logiciels de santé (ISO 13485, IEC 62304) recherche un Test Manager "
            "pour piloter une équipe de testeurs : stratégie de test risk-based testing, "
            "automatisation Selenium et Playwright, tests API avec KarateDSL et REST Assured, "
            "CI/CD GitLab, Jira, Squash TM, management d'équipe, pilotage des releases."
        ),
        "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score >= 85, result.breakdown


def test_offre_qa_junior_plafonnee(profile):
    offer = {
        "title": "Testeur QA junior",
        "company": "ESN",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Testeur débutant, tests manuels, Jira.",
        "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score <= 30


def test_offre_hors_qa_plafonnee(profile):
    offer = {
        "title": "Développeur PHP Symfony",
        "company": "Agence web",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Développement backend PHP, MySQL, déploiement continu.",
        "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score <= 20


def test_remote_compense_la_distance(profile):
    offer_paris = {
        "title": "QA Lead",
        "company": "Scale-up",
        "location": "Paris",
        "contract_type": "CDI",
        "description": "Pilotage QA, automatisation Cypress, management.",
        "remote": False,
    }
    offer_remote = dict(offer_paris, remote=True, description="Full remote. " + offer_paris["description"])
    score_paris = score_offer(offer_paris, profile).score
    score_remote = score_offer(offer_remote, profile).score
    assert score_remote > score_paris


def test_offre_lyon_mieux_classee_que_region(profile):
    base = {
        "title": "Test Manager",
        "company": "X",
        "contract_type": "CDI",
        "description": "Management de l'équipe QA, stratégie de test.",
        "remote": False,
    }
    lyon = score_offer(dict(base, location="Villeurbanne (69)"), profile).score
    grenoble = score_offer(dict(base, location="Grenoble (38)"), profile).score
    assert lyon > grenoble


def test_mot_cle_exclu_plafonne(profile):
    profile = dict(profile, excluded_keywords=["sopra steria"])
    offer = {
        "title": "Test Manager",
        "company": "Sopra Steria",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Poste chez Sopra Steria : pilotage QA.",
        "remote": False,
    }
    assert score_offer(offer, profile).score <= 10


def test_breakdown_explicable(profile):
    offer = {
        "title": "QA Engineer",
        "company": "Start-up",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Automatisation Playwright, CI/CD, Jira.",
        "remote": False,
    }
    result = score_offer(offer, profile)
    labels = [b["label"] for b in result.breakdown]
    assert "Adéquation du poste" in labels
    assert "Compétences du CV" in labels
    assert "Localisation" in labels
    assert all("detail" in b for b in result.breakdown)


def test_combined_score():
    assert combined_score(80, None) == 80
    assert combined_score(80, 60) == 70
    assert combined_score(50.5, 49.5) == 50.0
