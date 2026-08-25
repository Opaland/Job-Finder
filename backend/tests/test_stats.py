"""Tests de l'endpoint statistiques."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Offer, Profile, local_now


@pytest.fixture()
def client(db):
    """Client + jeu d'offres de référence, sur la base partagée (conftest.py)."""
    from fastapi.testclient import TestClient

    profile = db.get(Profile, 1)
    profile.cv_text = "cv"

    def add(status, score, source="france_travail", days_ago=0):
        add.n += 1
        db.add(Offer(
            fingerprint=f"fp{add.n}", source=source, source_id=str(add.n),
            title=f"Offre {add.n}", company="ACME", status=status,
            score=score, final_score=score,
            collected_at=local_now() - timedelta(days=days_ago),
        ))
    add.n = 0
    add("nouvelle", 92)
    add("vue", 75, source="adzuna")
    add("postulee", 88)
    add("entretien", 95)
    add("refusee", 40, days_ago=10)
    add("fermee", 15, days_ago=20)
    db.commit()

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def test_stats_totaux(client):
    data = client.get("/api/stats").json()
    t = data["totals"]
    assert t["offers"] == 6
    assert t["sent"] == 3           # postulée + entretien + refusée
    assert t["interviews"] == 1
    assert t["response_rate"] == 67  # 2 réponses / 3 envoyées
    assert t["new_7d"] == 4


def test_stats_repartitions(client):
    data = client.get("/api/stats").json()
    by_status = {s["status"]: s["count"] for s in data["by_status"]}
    assert by_status["nouvelle"] == 1 and by_status["entretien"] == 1
    by_source = {s["source"]: s["count"] for s in data["by_source"]}
    assert by_source["france_travail"] == 5 and by_source["adzuna"] == 1
    assert sum(b["count"] for b in data["score_bins"]) == 6
    assert len(data["per_day"]) == 30
    assert sum(d["count"] for d in data["per_day"]) == 6  # toutes collectées sous 30 jours


def test_pagination_tri_et_filtre_entreprise(client):
    """Pagination, tri par date de publication et filtre entreprise de la liste."""
    page1 = client.get("/api/offers?limit=2&offset=0").json()
    page2 = client.get("/api/offers?limit=2&offset=2").json()
    assert page1["total"] == 6 and len(page1["items"]) == 2 and len(page2["items"]) == 2
    assert {o["id"] for o in page1["items"]}.isdisjoint({o["id"] for o in page2["items"]})

    by_company = client.get("/api/offers?company=acm").json()
    assert by_company["total"] == 6  # toutes chez ACME dans la fixture

    published = client.get("/api/offers?sort=published").json()
    assert published["total"] == 6  # tri accepté (published_at nul → en fin de liste)


def test_reactivite_entreprises(client):
    """La réactivité par entreprise se calcule depuis l'historique des statuts."""
    from app.database import get_db

    # Récupère la session injectée pour enrichir l'historique de deux offres.
    db = next(iter(fastapi_app.dependency_overrides[get_db]()))
    now = local_now()
    o_reponse = db.query(Offer).filter(Offer.status == "entretien").one()
    o_reponse.company = "Rapide SAS"
    o_reponse.status_history = [
        {"status": "postulee", "date": (now - timedelta(days=10)).isoformat(), "par": "utilisateur"},
        {"status": "entretien", "date": (now - timedelta(days=6)).isoformat(), "par": "utilisateur"},
    ]
    o_attente = db.query(Offer).filter(Offer.status == "postulee").one()
    o_attente.company = "Silencieuse SARL"
    o_attente.status_history = [
        {"status": "postulee", "date": (now - timedelta(days=12)).isoformat(), "par": "utilisateur"},
    ]
    db.commit()

    companies = {c["company"]: c for c in client.get("/api/stats").json()["companies"]}
    assert companies["Rapide SAS"]["responses"] == 1
    assert companies["Rapide SAS"]["avg_response_days"] == 4
    assert companies["Silencieuse SARL"]["responses"] == 0
    assert companies["Silencieuse SARL"]["pending_days"] == 12


def test_historique_sante_des_sources(client):
    """L'historique ok/erreur par source se construit depuis les derniers scans."""
    from app.database import get_db
    from app.models import ScanRun

    db = next(iter(fastapi_app.dependency_overrides[get_db]()))
    db.add_all([
        ScanRun(status="termine", trigger="quotidien", source_stats={
            "france_travail": {"label": "FT", "fetched": 10, "new": 2, "errors": []},
            "hellowork": {"label": "HW", "fetched": 0, "new": 0, "errors": ["panne"]},
            "wttj": {"label": "W", "skipped": True},
        }),
        ScanRun(status="termine", trigger="quotidien", source_stats={
            "france_travail": {"label": "FT", "fetched": 12, "new": 0, "errors": []},
        }),
    ])
    db.commit()

    sources = {s["name"]: s for s in client.get("/api/sources").json()["sources"]}
    assert [h["ok"] for h in sources["france_travail"]["history"]] == [True, True]
    assert [h["ok"] for h in sources["hellowork"]["history"]] == [False]
    assert sources["wttj"]["history"] == []  # scan sauté : pas compté


def test_stats_base_vide(tmp_path):
    from fastapi.testclient import TestClient

    engine = create_engine(f"sqlite:///{tmp_path}/vide.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    db.add(Profile(id=1, sources_enabled={}))
    db.commit()

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        data = TestClient(fastapi_app).get("/api/stats").json()
        assert data["totals"]["response_rate"] is None
        assert data["totals"]["avg_top20"] is None
    finally:
        fastapi_app.dependency_overrides.clear()
        db.close()


# --- Sprint 31 : ce que rapporte chaque source ------------------------------

def test_conversion_par_source(client, db):
    """Taux d'entretien = entretiens / candidatures, par source."""
    from app.models import Offer, local_now

    def offre(source_id, source, statuts):
        historique = [{"status": s, "date": local_now().isoformat(), "par": "test"} for s in statuts]
        db.add(Offer(fingerprint=f"fp-{source_id}", source=source, source_id=source_id,
                     title="QA", company="ACME", final_score=70.0,
                     status=statuts[-1], status_history=historique))

    offre("a1", "apec", ["nouvelle", "postulee", "entretien"])
    offre("a2", "apec", ["nouvelle", "postulee"])
    offre("h1", "hellowork", ["nouvelle", "postulee"])
    offre("h2", "hellowork", ["nouvelle"])
    db.commit()

    lignes = {s["source"]: s for s in client.get("/api/stats").json()["conversion_sources"]}
    assert lignes["apec"]["candidatures"] == 2
    assert lignes["apec"]["entretiens"] == 1
    assert lignes["apec"]["taux_entretien"] == 50
    assert lignes["hellowork"]["candidatures"] == 1
    assert lignes["hellowork"]["taux_entretien"] == 0


def test_source_sans_candidature_na_pas_de_taux(client, db):
    from app.models import Offer
    db.add(Offer(fingerprint="fp-z", source="wttj", source_id="z", title="QA",
                 company="ACME", final_score=50.0, status="nouvelle"))
    db.commit()
    ligne = next(s for s in client.get("/api/stats").json()["conversion_sources"] if s["source"] == "wttj")
    assert ligne["taux_entretien"] is None
    assert ligne["offres"] == 1
