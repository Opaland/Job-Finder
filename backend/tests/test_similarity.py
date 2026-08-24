"""Tests de la détection de doublons par similarité de titre."""
from app.services.textutils import canonical_title, titles_similar


def test_canonisation():
    assert canonical_title("Test Manager H/F") == "test manager"
    assert canonical_title("Test Manager (F/H) - CDI") == "test manager"
    assert canonical_title("QA Lead – Freelance – URGENT") == "qa lead"


def test_variantes_du_meme_poste():
    assert titles_similar("Test Manager H/F", "Test Manager (F/H) - CDI")
    assert titles_similar("QA Lead", "Lead QA")  # mêmes mots, ordre différent
    assert titles_similar("Responsable Test et Qualité", "Responsable test / qualité")
    assert titles_similar("Test Manager Santé H/F", "Test manager santé")


def test_postes_differents_non_confondus():
    assert not titles_similar("Test Manager", "Développeur Java")
    assert not titles_similar("QA Lead", "QA Engineer junior")
    assert not titles_similar("Testeur QA", "Test Manager")
    assert not titles_similar("", "Test Manager")


def test_fusion_au_scan_meme_entreprise(tmp_path, monkeypatch):
    """Deux sources, même entreprise, titres 'H/F' vs '(F/H) CDI' → une seule fiche."""
    import json
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.services.scan as scan_module
    from app.connectors.base import ConnectorResult, RawOffer
    from app.database import Base
    from app.models import Offer, Profile
    from app.services.scan import run_scan

    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    seed = json.loads(
        (Path(__file__).resolve().parent.parent / "seed" / "profile_seed.json").read_text(encoding="utf-8")
    )
    db.add(Profile(id=1, cv_text=seed["cv_text"], target_titles=seed["target_titles"],
                   skills=["jira"], location_keywords=["lyon"], contracts=["CDI"],
                   sector_bonus=[], excluded_keywords=[], sources_enabled={}))
    db.commit()
    monkeypatch.setattr(scan_module, "cli_available", lambda: False)

    class C1:
        name, label, needs_key = "s1", "S1", False
        def is_configured(self): return True
        def fetch(self, profile):
            return ConnectorResult(offers=[RawOffer(
                source="s1", source_id="1", title="Test Manager H/F",
                company="ACME Santé", location="Lyon", description="d", url="https://a/1")])

    class C2:
        name, label, needs_key = "s2", "S2", False
        def is_configured(self): return True
        def fetch(self, profile):
            return ConnectorResult(offers=[
                RawOffer(source="s2", source_id="9", title="Test Manager (F/H) - CDI",
                         company="ACME Santé", location="Lyon", description="d", url="https://b/9"),
                RawOffer(source="s2", source_id="10", title="Développeur Java",
                         company="ACME Santé", location="Lyon", description="d", url="https://b/10"),
                RawOffer(source="s2", source_id="11", title="Test Manager H/F",
                         company="Autre Entreprise", location="Lyon", description="d", url="https://b/11"),
            ])

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [C1(), C2()])
    run = run_scan(db, trigger="manuel")

    offers = db.query(Offer).all()
    titles = sorted(o.title for o in offers)
    # 3 fiches : le doublon ACME a été fusionné, le poste différent et
    # l'autre entreprise restent distincts.
    assert len(offers) == 3, titles
    merged = next(o for o in offers if o.company == "ACME Santé" and "Test Manager" in o.title)
    assert any(s["source"] == "s2" for s in merged.other_sources)
    assert run.new_count == 3 and run.seen_count == 1
    db.close()
