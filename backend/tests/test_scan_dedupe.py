"""Tests de l'orchestration du scan : dédoublonnage, jamais de fermeture automatique."""
import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.scan as scan_module
from app.connectors.base import ConnectorResult, RawOffer
from app.database import Base
from app.models import Offer, Profile, local_now
from app.services.scan import run_scan


class FakeConnector:
    name = "fake"
    label = "Fake"
    needs_key = False

    def __init__(self, offers):
        self._offers = offers

    def is_configured(self):
        return True

    def fetch(self, profile):
        return ConnectorResult(offers=list(self._offers))


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    seed = json.loads(
        (Path(__file__).resolve().parent.parent / "seed" / "profile_seed.json").read_text(encoding="utf-8")
    )
    session.add(
        Profile(
            id=1,
            cv_text=seed["cv_text"],
            target_titles=seed["target_titles"],
            skills=["selenium", "jira"],
            location_keywords=seed["location_keywords"],
            contracts=seed["contracts"],
            sector_bonus=seed["sector_bonus"],
            excluded_keywords=[],
            sources_enabled={},
        )
    )
    session.commit()
    # Pas d'IA pendant les tests.
    monkeypatch.setattr(scan_module, "cli_available", lambda: False)
    yield session
    session.close()


def _offer(source_id="1", title="Test Manager", company="ACME", source_list=None):
    return RawOffer(
        source="fake",
        source_id=source_id,
        title=title,
        company=company,
        location="Lyon",
        description="Pilotage QA, Selenium, Jira.",
        url=f"https://example.com/{source_id}",
        contract_type="CDI",
    )


def test_scan_insere_et_score(db, monkeypatch):
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run = run_scan(db, trigger="manuel")
    assert run.new_count == 1
    offer = db.query(Offer).one()
    assert offer.score > 0
    assert offer.status == "nouvelle"
    assert offer.final_score == offer.score


def test_scan_ne_duplique_pas(db, monkeypatch):
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    run2 = run_scan(db, trigger="manuel")
    assert run2.new_count == 0
    assert run2.seen_count == 1
    assert db.query(Offer).count() == 1


def test_meme_offre_deux_sources_fusionnee(db, monkeypatch):
    offer_a = _offer(source_id="a")
    offer_b = RawOffer(
        source="fake2", source_id="b", title="Test Manager", company="ACME",
        location="Lyon", description="desc", url="https://autre.com/b",
    )
    fake2 = FakeConnector([offer_b])
    fake2.name = "fake2"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([offer_a]), fake2])
    run_scan(db, trigger="manuel")
    assert db.query(Offer).count() == 1
    offer = db.query(Offer).one()
    assert any(s["source"] == "fake2" for s in offer.other_sources)


def test_entreprises_vides_jamais_fusionnees(db, monkeypatch):
    """Deux offres au même titre mais d'entreprises inconnues restent distinctes."""
    offer_a = RawOffer(source="fake", source_id="x1", title="Test Manager H/F",
                       company="", location="Lyon", description="d", url="https://a/1")
    offer_b = RawOffer(source="fake2", source_id="x2", title="Test Manager H/F",
                       company="", location="Paris", description="d", url="https://b/2")
    fake2 = FakeConnector([offer_b])
    fake2.name = "fake2"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([offer_a]), fake2])
    run_scan(db, trigger="manuel")
    assert db.query(Offer).count() == 2


def test_offre_manuelle_jamais_hors_ligne(db, monkeypatch):
    """Une offre ajoutée à la main n'est jamais marquée « plus en ligne » par un scan."""
    manual = Offer(fingerprint="fp-man", source="manuelle", source_id="m1",
                   title="Offre LinkedIn collée", status="postulee", final_score=80,
                   last_seen_at=local_now() - timedelta(days=30))
    db.add(manual)
    db.commit()
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    db.expire_all()
    assert db.query(Offer).filter_by(source="manuelle").one().still_online is True


def test_offre_disparue_jamais_fermee(db, monkeypatch):
    """Une offre plus vue à la source passe hors-ligne mais garde son statut."""
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    offer = db.query(Offer).one()
    offer.status = "postulee"
    offer.last_seen_at = local_now() - timedelta(days=30)
    db.commit()

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([])])
    run_scan(db, trigger="manuel")
    db.expire_all()  # l'UPDATE en masse ne rafraîchit pas les objets déjà chargés
    offer = db.query(Offer).one()
    assert offer.still_online is False
    assert offer.status == "postulee"  # le statut n'est JAMAIS modifié par un scan


def test_connecteur_en_erreur_ne_bloque_pas(db, monkeypatch):
    class Broken(FakeConnector):
        def fetch(self, profile):
            raise RuntimeError("panne")

    monkeypatch.setattr(
        scan_module, "ALL_CONNECTORS", [Broken([]), FakeConnector([_offer()])]
    )
    run = run_scan(db, trigger="manuel")
    assert run.new_count == 1
    assert run.status == "termine"
