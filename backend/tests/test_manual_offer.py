"""Tests de l'ajout manuel d'offres (annonce collée)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Offer, Profile

ANNONCE = """Test Manager H/F
ACME Santé
Lyon — CDI — télétravail partiel

ACME Santé, éditeur de logiciels médicaux (ISO 13485), cherche un Test Manager
pour piloter son équipe QA : stratégie de test, automatisation Selenium et
KarateDSL, management de 5 testeurs, CI/CD GitLab, Jira et Squash TM.
"""


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    seed = json.loads(
        (Path(__file__).resolve().parent.parent / "seed" / "profile_seed.json").read_text(encoding="utf-8")
    )
    db.add(Profile(id=1, cv_text=seed["cv_text"], target_titles=seed["target_titles"],
                   skills=["selenium", "karatedsl", "jira", "management"],
                   location_keywords=seed["location_keywords"], contracts=["CDI"],
                   sector_bonus=seed["sector_bonus"], excluded_keywords=[], sources_enabled={}))
    db.commit()

    def override():
        yield db

    fastapi_app.dependency_overrides[get_db] = override
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()
    db.close()


def test_annonce_collee_parsee_et_scoree(client):
    resp = client.post("/api/offers/manual", json={"raw_text": ANNONCE, "url": "https://www.linkedin.com/jobs/x"})
    assert resp.status_code == 201, resp.text
    offer = resp.json()
    assert offer["title"] == "Test Manager H/F"      # 1re ligne
    assert offer["company"] == "ACME Santé"           # 2e ligne
    assert offer["contract_type"] == "CDI"
    assert offer["remote"] is True
    assert offer["source"] == "manuelle"
    assert offer["final_score"] >= 80                 # poste cible + compétences + Lyon
    assert offer["status"] == "nouvelle"


def test_titre_explicite_prioritaire(client):
    resp = client.post("/api/offers/manual", json={
        "title": "QA Lead", "company": "Startup", "raw_text": "Description libre sans structure.",
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "QA Lead"


def test_sans_rien_refuse(client):
    resp = client.post("/api/offers/manual", json={"raw_text": ""})
    assert resp.status_code == 400


def test_doublon_detecte(client):
    assert client.post("/api/offers/manual", json={"raw_text": ANNONCE}).status_code == 201
    # Même offre, titre légèrement différent → refusée avec un message actionnable.
    resp = client.post("/api/offers/manual", json={
        "title": "Test Manager (F/H) - CDI", "company": "ACME Santé", "raw_text": "desc",
    })
    assert resp.status_code == 409
    assert "déjà suivie" in resp.json()["detail"]
