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
from app.services.scan import offer_to_scoring_dict, profile_to_dict, run_scan


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
    """Une offre plus vue à la source passe hors-ligne mais garde son statut.

    La source doit avoir réellement ramené des offres : c'est ce qui permet de
    conclure que celle-ci a bien disparu.
    """
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    offer = db.query(Offer).one()
    offer.status = "postulee"
    offer.last_seen_at = local_now() - timedelta(days=30)
    db.commit()

    # La source répond normalement, avec d'autres offres : l'ancienne a disparu.
    autre = _offer(source_id="autre-annonce", title="QA Engineer")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([autre])])
    run_scan(db, trigger="manuel")
    db.expire_all()  # l'UPDATE en masse ne rafraîchit pas les objets déjà chargés
    ancienne = db.query(Offer).filter(Offer.source_id != "autre-annonce").one()
    assert ancienne.still_online is False
    assert ancienne.status == "postulee"      # la règle absolue tient


def test_une_source_qui_ne_ramene_rien_ne_declare_personne_hors_ligne(db, monkeypatch):
    """Régression : une source dont le format change répond « 200 OK, 0 offre ».

    Le scan ne peut RIEN en conclure. Avant ce correctif, toutes ses offres —
    pourtant bien en ligne — se couvraient du chip « Plus en ligne ? » au 15e
    jour, sans qu'aucune erreur ne soit affichée nulle part.
    """
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    offer = db.query(Offer).one()
    offer.last_seen_at = local_now() - timedelta(days=30)
    db.commit()

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([])])
    run_scan(db, trigger="manuel")
    db.expire_all()
    assert db.query(Offer).one().still_online is True


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


def test_profile_to_dict_reprend_bien_toutes_les_listes_et_le_salaire_minimum(db):
    """Helper canonique (point de passage unique profil → scoring, issue #19) :
    aucun test ne l'exerçait directement. Vérifié par mutation lors de l'audit
    que `profile.skills or []` → `profile.skills and []` fait disparaître les
    compétences du CV en silence sans qu'aucun test existant ne le remarque."""
    profil = db.get(Profile, 1)
    profil.skills = ["Selenium", "Cypress", "Jira"]
    profil.target_titles = ["Test Manager"]
    profil.min_salary = 55000
    d = profile_to_dict(profil)
    assert d["skills"] == ["Selenium", "Cypress", "Jira"]
    assert d["target_titles"] == ["Test Manager"]
    assert d["min_salary"] == 55000


def test_offer_to_scoring_dict_reprend_le_texte_du_salaire(db):
    offre = Offer(fingerprint="fp-sal", source="fake", source_id="sal", title="Test Manager",
                  company="ACME", salary_text="45 000 - 50 000 € / an")
    assert offer_to_scoring_dict(offre)["salary_text"] == "45 000 - 50 000 € / an"


def test_offre_revue_redevient_en_ligne(db, monkeypatch):
    """Moitié jamais testée de la règle absolue du scan (issue #18) : une
    disparition met still_online à False, mais rien ne prouvait que l'offre
    redevient True si la source la revoit. Vérifié par mutation lors de
    l'audit : remplacer `existing.still_online = True` par `pass` laissait
    les 9 tests d'alors tous verts."""
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    offer = db.query(Offer).one()
    offer.still_online = False   # simulation d'une disparition passée
    offer.status = "postulee"
    db.commit()

    # Même source, même source_id : l'offre est bien de nouveau là.
    run_scan(db, trigger="manuel")
    db.expire_all()
    offer = db.query(Offer).one()
    assert offer.still_online is True
    assert offer.status == "postulee"   # la règle absolue tient : statut jamais touché


def test_offre_revue_via_une_autre_source_redevient_en_ligne(db, monkeypatch):
    """Même règle, chemin « jumeau » (scan.py:~220) : l'offre reparaît via une
    AUTRE source, même entreprise et titre proche — pas le même source_id."""
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    offer = db.query(Offer).one()
    offer.still_online = False
    db.commit()

    jumeau = _offer(source_id="autre-source-id", title="Test Manager H/F")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([jumeau])])
    run_scan(db, trigger="manuel")
    db.expire_all()
    assert db.query(Offer).count() == 1   # fusionnée, pas dupliquée
    assert db.query(Offer).one().still_online is True


def test_le_scan_detecte_une_source_qui_reussit_a_vide(db, monkeypatch):
    """Issue #14 : ni le scan planifié ni /api/sources n'appelaient
    diagnostic.py — une source qui répond, ramène des offres, mais avec un
    champ vide sur toutes (mapping cassé) passait pour un scan normal.
    Vérifié ici SANS deuxième appel réseau : la détection réutilise les
    offres déjà récupérées par ce même scan."""
    offres = [_offer(source_id="1", company=""), _offer(source_id="2", company="")]
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector(offres)])
    run = run_scan(db, trigger="manuel")
    assert run.source_stats["fake"]["champs_vides"] == ["company"]


def test_connecteur_en_erreur_donne_un_message_francais_pas_la_trace_python(db, monkeypatch):
    """Le filet de sécurité du scan (si un connecteur viole son contrat et laisse
    fuiter une exception) doit passer par resume_erreur(), pas str(exc) brut —
    sinon Sources & réglages affiche une trace Python au lieu d'une phrase
    française actionnable."""
    class CasseAvecTraceLaide(FakeConnector):
        name = "casse"
        label = "Source cassée"

        def fetch(self, profile):
            raise KeyError("champ_improbable_x7")

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [CasseAvecTraceLaide([])])
    run = run_scan(db, trigger="manuel")
    assert run.source_stats["casse"]["errors"] == ["Erreur inattendue : 'champ_improbable_x7'"]


def test_description_enrichie_declenche_un_nouveau_score(db, monkeypatch):
    """Régression : une offre reçue d'abord en extrait gardait son score bas.

    Le scan complétait la description mais ne recalculait pas le score : une
    offre parfaite arrivée tronquée ne devenait jamais une pépite.
    """
    extrait = RawOffer(source="fake", source_id="enr1", title="Test Manager",
                       company="Éditeur santé", location="Lyon", contract_type="CDI",
                       description="Poste de Test Manager.")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([extrait])])
    run_scan(db, trigger="test")
    offre = db.query(Offer).filter(Offer.source_id == "enr1").one()
    score_extrait, ia_avant = offre.score, offre.ai_score

    complet = RawOffer(source="fake", source_id="enr1", title="Test Manager",
                       company="Éditeur santé", location="Lyon", contract_type="CDI",
                       description=("Pilotage de la stratégie de test, automatisation Selenium "
                                    "et Playwright, tests API KarateDSL, CI/CD GitLab, Jira, "
                                    "management d'une équipe de testeurs, ISO 13485."))
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([complet])])
    run_scan(db, trigger="test")
    db.refresh(offre)

    assert offre.description.startswith("Pilotage")     # description bien remplacée
    assert offre.score > score_extrait, (
        f"score resté à {score_extrait} alors que la description cite les compétences du CV"
    )
    detail = " ".join(b["detail"] for b in offre.score_breakdown)
    assert "Aucune compétence" not in detail
    assert ia_avant is None or offre.ai_score is None    # avis IA périmé retiré


def test_affinage_ia_respecte_un_budget_de_temps(db, monkeypatch):
    """Un affinage IA anormalement lent s'arrête avant d'avoir tout traité.

    Avec un ai_max_offers_per_scan réglé haut et jusqu'à 300s de timeout CLI par
    offre, le pire cas dépasse l'ExecutionTimeLimit d'1h de la tâche planifiée
    Windows — le scan doit s'arrêter de lui-même plutôt que de risquer de ne
    jamais construire le digest/email. Les offres non affinées restent
    candidates (ai_score=None) pour le prochain scan.
    """
    offres = [
        _offer(source_id="1", title="Test Manager", company="Alpha"),
        _offer(source_id="2", title="QA Lead", company="Beta"),
    ]
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector(offres)])
    monkeypatch.setattr(scan_module, "cli_available", lambda: True)
    monkeypatch.setattr(scan_module, "ai_score_offer", lambda offer_dict, cv_text: (88.0, "raison test"))

    # ai_debut=0, 1er tour (0 - 0 = 0, sous le budget) : affine la 1re offre.
    # 2e tour (budget+1 - 0, dépassé) : s'arrête avant la 2e offre.
    horloge = iter([0.0, 0.0, scan_module.AI_BUDGET_SECONDES + 1])
    monkeypatch.setattr(scan_module.time, "monotonic", lambda: next(horloge))

    run_scan(db, trigger="test")

    offres_en_base = db.query(Offer).order_by(Offer.score.desc()).all()
    scores_ia = [o.ai_score for o in offres_en_base]
    assert scores_ia.count(88.0) == 1, "une seule offre aurait dû être affinée avant la coupure"
    assert scores_ia.count(None) == 1, "l'offre restante doit rester candidate pour le prochain scan"
