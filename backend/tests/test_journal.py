"""Tests du journal d'activité."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Offer, Profile


@pytest.fixture()
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    db.add(Profile(id=1, sources_enabled={}))
    db.add(Offer(fingerprint="fp1", source="test", source_id="1",
                 title="Test Manager", company="ACME", status="nouvelle", final_score=80))
    db.commit()

    def override():
        yield db

    fastapi_app.dependency_overrides[get_db] = override
    yield {"db": db, "client": TestClient(fastapi_app)}
    fastapi_app.dependency_overrides.clear()
    db.close()


def test_changement_de_statut_journalise(env):
    offer_id = env["db"].query(Offer).one().id
    env["client"].patch(f"/api/offers/{offer_id}", json={"status": "postulee"})

    entries = env["client"].get("/api/journal").json()
    assert len(entries) == 1
    assert entries[0]["kind"] == "statut"
    assert "nouvelle → postulee" in entries[0]["message"]
    assert entries[0]["offer_id"] == offer_id


def test_filtre_par_type(env):
    from app.services.journal import log_event

    log_event(env["db"], "scan", "Scan terminé.")
    log_event(env["db"], "cv", "CV importé.")

    assert len(env["client"].get("/api/journal").json()) == 2
    only_scan = env["client"].get("/api/journal?kind=scan").json()
    assert len(only_scan) == 1 and only_scan[0]["kind"] == "scan"


def test_journal_ne_casse_jamais_l_action(env, monkeypatch):
    """Si l'écriture du journal échoue, l'action tracée aboutit quand même."""
    import app.services.journal as journal_module

    def boom(*args, **kwargs):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(journal_module.ActivityLog, "__init__", boom)
    offer_id = env["db"].query(Offer).one().id
    resp = env["client"].patch(f"/api/offers/{offer_id}", json={"status": "vue"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "vue"


def test_type_inconnu_explique_les_types_possibles(env):
    resp = env["client"].get("/api/journal?kind=nimportequoi")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "nimportequoi" in detail and "restauration" in detail


def test_tous_les_types_journalises_sont_declares():
    """KINDS doit rester le miroir de ce que le code écrit réellement."""
    import re
    from pathlib import Path

    from app.services.journal import KINDS

    racine = Path(__file__).resolve().parent.parent / "app"
    ecrits = {
        m.group(1)
        for fichier in racine.rglob("*.py")
        for m in re.finditer(r'log_event\(\s*\w+\s*,\s*"([a-z_]+)"', fichier.read_text(encoding="utf-8"))
    }
    assert ecrits <= set(KINDS), f"types journalisés absents de KINDS : {ecrits - set(KINDS)}"
