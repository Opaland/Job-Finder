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
from app.services.scan import (
    enrichir_description,
    find_twin,
    index_offres_connues,
    offer_to_scoring_dict,
    profile_to_dict,
    rescore_all,
    run_full_scan,
    run_scan,
)


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


def test_scan_status_vrai_pendant_le_scan_et_faux_apres(db, monkeypatch):
    """Doit être le TOUT PREMIER test du module : `_current_scan` est une
    valeur par défaut au niveau du module (`{"running": False, ...}`,
    scan.py:31), jamais réaffectée avant le premier scan. Un seul scan déjà
    lancé par un test précédent dans le même process suffit à masquer pour
    toujours une mutation de ce littéral initial — ce test doit donc rester
    en tête de fichier."""
    vu_pendant = []

    class ConnecteurObservateur(FakeConnector):
        def fetch(self, profile):
            vu_pendant.append(scan_module.scan_status()["running"])
            return ConnectorResult(offers=list(self._offers))

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [ConnecteurObservateur([_offer()])])
    assert scan_module.scan_status()["running"] is False
    run_scan(db, trigger="manuel")
    assert vu_pendant == [True]
    assert scan_module.scan_status()["running"] is False


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


def test_offre_close_par_lutilisateur_jamais_touchee_par_une_disparition_puis_un_retour(db, monkeypatch):
    """Règle absolue du scan, cas le plus sensible : une offre que Cédric a
    lui-même refusée (`STATUTS_CLOS`) ne doit JAMAIS voir son statut bouger —
    ni quand elle disparaît de la source, ni quand elle y réapparaît."""
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run_scan(db, trigger="manuel")
    offer = db.query(Offer).one()
    offer.status = "refusee"
    offer.last_seen_at = local_now() - timedelta(days=30)
    db.commit()

    # Disparition : une autre offre est ramenée, celle-ci non.
    autre = _offer(source_id="autre-annonce-close", title="QA Engineer")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([autre])])
    run_scan(db, trigger="manuel")
    db.expire_all()
    offer = db.query(Offer).filter(Offer.source_id == "1").one()
    assert offer.still_online is False
    assert offer.status == "refusee"

    # Retour : la même source ramène à nouveau l'offre refusée.
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer(), autre])])
    run_scan(db, trigger="manuel")
    db.expire_all()
    offer = db.query(Offer).filter(Offer.source_id == "1").one()
    assert offer.still_online is True
    assert offer.status == "refusee"   # jamais réouverte malgré son retour


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
    # Le connecteur a levé avant que `fetched`/`new`/`seen` ne soient jamais mis
    # à jour : ils gardent leurs valeurs initiales, jamais incrémentées par erreur.
    assert run.source_stats["casse"]["fetched"] == 0
    assert run.source_stats["casse"]["new"] == 0
    assert run.source_stats["casse"]["seen"] == 0


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


# --- Sprint 61 : trous relevés par mutation testing (scan.py) -----------------

def test_profile_to_dict_toutes_les_listes_a_none_ne_plantent_pas(db):
    """Les six champs liste/dict du profil (hors skills/target_titles, déjà
    couverts) doivent retomber sur [] / {} quand ils valent None en base —
    sinon un `or` devenu `and` fait planter le scan au premier appel."""
    profil = db.get(Profile, 1)
    profil.location_keywords = None
    profil.contracts = None
    profil.sector_bonus = None
    profil.excluded_keywords = None
    profil.scoring_weights = None
    profil.search_queries = None
    d = profile_to_dict(profil)
    assert d["location_keywords"] == []
    assert d["contracts"] == []
    assert d["sector_bonus"] == []
    assert d["excluded_keywords"] == []
    assert d["scoring_weights"] == {}
    assert d["search_queries"] == []


def test_enrichir_description_meme_longueur_ne_remplace_pas(db):
    """`<=` strict : une description de MÊME longueur n'est pas considérée
    plus riche — sinon chaque revue du scan recalculerait le score pour rien."""
    offre = Offer(fingerprint="fp-e1", source="fake", source_id="e1", title="t",
                  company="c", description="1234567890", ai_score=70.0, ai_reason="avis existant")
    raw = _offer(source_id="e1")
    raw.description = "abcdefghij"  # même longueur (10), pas plus riche
    assert enrichir_description(offre, raw, profile_to_dict(db.get(Profile, 1))) is False
    assert offre.description == "1234567890"
    assert offre.ai_score == 70.0  # avis IA non réinitialisé puisque rien n'a changé


def test_enrichir_description_source_sans_description_ne_plante_pas(db):
    """`raw.description or ""` : une source qui ne fournit aucune description
    (None) ne doit jamais planter la comparaison de longueurs."""
    offre = Offer(fingerprint="fp-e2", source="fake", source_id="e2", title="t",
                  company="c", description="une description déjà présente")
    raw = _offer(source_id="e2")
    raw.description = None
    assert enrichir_description(offre, raw, profile_to_dict(db.get(Profile, 1))) is False
    assert offre.description == "une description déjà présente"


def test_enrichir_description_plus_riche_remplace_et_reinitialise_lavis_ia(db):
    offre = Offer(fingerprint="fp-e3", source="fake", source_id="e3", title="Test Manager",
                  company="c", description="court", ai_score=70.0, ai_reason="ancien avis")
    raw = _offer(source_id="e3")
    raw.description = "Une description nettement plus longue et détaillée que l'originale."
    profile_dict = profile_to_dict(db.get(Profile, 1))
    assert enrichir_description(offre, raw, profile_dict) is True
    assert offre.description == raw.description
    assert offre.ai_score is None
    assert offre.ai_reason == ""


def test_find_twin_sans_index_fournis_interroge_directement_la_base(db):
    """Chemin DB (fingerprints=None, company_index=None) : utilisé par l'import
    CSV, jamais exercé par les tests qui passent toujours les dicts du scan."""
    existante = Offer(fingerprint="fp-twin1", source="fake", source_id="x1",
                      title="Test Manager Senior", company="Capgemini")
    db.add(existante)
    db.commit()
    jumeau = find_twin(db, "Test Manager Senior H/F", "Capgemini")
    assert jumeau is not None
    assert jumeau.id == existante.id
    assert find_twin(db, "Développeur Python", "Entreprise Inconnue XYZ") is None


def test_find_twin_entreprise_de_deux_lettres_jamais_fusionnee_par_titre(db):
    """< 3 caractères normalisés : seule l'empreinte exacte peut fusionner —
    jamais le rapprochement par titre proche, trop risqué sur un nom aussi court."""
    existante = Offer(fingerprint="fp-twin2", source="fake", source_id="x2",
                      title="Test Manager H/F", company="IT")
    db.add(existante)
    db.commit()
    # Même titre, même entreprise courte, mais empreinte différente (title2 != title).
    assert find_twin(db, "Test Manager", "IT") is None


def test_find_twin_entreprise_de_trois_lettres_peut_fusionner_par_titre(db):
    """Pile 3 caractères normalisés : le rapprochement par titre proche doit
    fonctionner — la frontière exacte de la règle « >= 3 »."""
    existante = Offer(fingerprint="fp-twin3", source="fake", source_id="x3",
                      title="Test Manager Senior", company="EDF")
    db.add(existante)
    db.commit()
    jumeau = find_twin(db, "Test Manager Senior H/F", "EDF")
    assert jumeau is not None
    assert jumeau.id == existante.id


def test_index_offres_connues_limite_lindex_entreprise_a_3_caracteres(db):
    courte = Offer(fingerprint="fp-idx1", source="fake", source_id="i1",
                   title="A", company="IT")
    longue = Offer(fingerprint="fp-idx2", source="fake", source_id="i2",
                   title="B", company="EDF")
    db.add_all([courte, longue])
    db.commit()
    _, _, company_index = index_offres_connues(db)
    assert "it" not in company_index
    assert "edf" in company_index


def test_run_scan_refuse_un_second_scan_concurrent(db, monkeypatch):
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    scan_module._scan_lock.acquire(blocking=False)
    try:
        with pytest.raises(RuntimeError, match="déjà en cours"):
            run_scan(db, trigger="manuel")
    finally:
        scan_module._scan_lock.release()


def test_sources_enabled_a_none_traite_toutes_les_sources_comme_actives(db, monkeypatch):
    profil = db.get(Profile, 1)
    profil.sources_enabled = None
    db.commit()
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run = run_scan(db, trigger="manuel")  # ne doit pas planter (AttributeError sur None.get)
    assert run.new_count == 1


def test_source_desactivee_est_marquee_skipped_et_ne_compte_pour_rien(db, monkeypatch):
    profil = db.get(Profile, 1)
    profil.sources_enabled = {"fake": False}
    db.commit()
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run = run_scan(db, trigger="manuel")
    assert run.source_stats["fake"]["skipped"] is True
    assert run.new_count == 0
    assert run.seen_count == 0
    assert db.query(Offer).count() == 0


def test_offre_sans_titre_ou_sans_identifiant_est_ignoree(db, monkeypatch):
    sans_titre = RawOffer(source="fake", source_id="st1", title="", company="ACME")
    sans_id = RawOffer(source="fake", source_id="", title="QA Engineer", company="ACME")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([sans_titre, sans_id])])
    run = run_scan(db, trigger="manuel")
    assert run.new_count == 0
    assert db.query(Offer).count() == 0


def test_jumeau_garde_les_anciennes_autres_sources_en_ajoutant_une_nouvelle(db, monkeypatch):
    """`others = list(twin.other_sources or [])` : un `or` devenu `and` repart
    toujours de [] et PERD les sources déjà notées lors d'une fusion précédente."""
    base = _offer(source_id="base")
    fake2 = FakeConnector([RawOffer(source="fake2", source_id="s2", title="Test Manager",
                                     company="ACME", url="https://deux.com/2")])
    fake2.name = "fake2"
    fake3 = FakeConnector([RawOffer(source="fake3", source_id="s3", title="Test Manager",
                                     company="ACME", url="https://trois.com/3")])
    fake3.name = "fake3"

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([base])])
    run_scan(db, trigger="manuel")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [fake2])
    run_scan(db, trigger="manuel")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [fake3])
    run_scan(db, trigger="manuel")

    db.expire_all()
    offre = db.query(Offer).one()
    sources_notees = {s["source"] for s in offre.other_sources}
    assert sources_notees == {"fake2", "fake3"}


def test_jumeau_najoute_pas_dentree_sans_url_en_double_ou_identique_au_principal(db, monkeypatch):
    """`raw.url and entry not in others and raw.url != twin.url` : chacune des
    trois conditions doit vraiment empêcher l'ajout, pas seulement « aider »."""
    base = _offer(source_id="base")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([base])])
    run_scan(db, trigger="manuel")
    url_principale = db.query(Offer).one().url

    # 1) URL vide côté jumeau : rien à ajouter.
    sans_url = FakeConnector([RawOffer(source="fake2", source_id="s2", title="Test Manager",
                                        company="ACME", url="")])
    sans_url.name = "fake2"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [sans_url])
    run_scan(db, trigger="manuel")

    # 2) URL identique à celle de l'offre principale : rien à ajouter.
    meme_url = FakeConnector([RawOffer(source="fake3", source_id="s3", title="Test Manager",
                                        company="ACME", url=url_principale)])
    meme_url.name = "fake3"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [meme_url])
    run_scan(db, trigger="manuel")

    db.expire_all()
    assert db.query(Offer).one().other_sources == []

    # 3) Doublon exact d'une entrée déjà notée : pas de deuxième copie.
    nouvelle = FakeConnector([RawOffer(source="fake4", source_id="s4", title="Test Manager",
                                        company="ACME", url="https://quatre.com/4")])
    nouvelle.name = "fake4"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [nouvelle])
    run_scan(db, trigger="manuel")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [nouvelle])
    run_scan(db, trigger="manuel")
    db.expire_all()
    assert db.query(Offer).one().other_sources == [{"source": "fake4", "url": "https://quatre.com/4"}]


def test_champs_de_la_nouvelle_offre_tronques_et_valeurs_absentes_videes(db, monkeypatch):
    longue = RawOffer(
        source="fake", source_id="long1", title="T" * 350, company="C" * 250,
        location="L" * 250, contract_type="X" * 80, salary_text="S" * 250,
        url="https://x.com/1",
    )
    sans_rien = RawOffer(source="fake", source_id="vide1", title="Titre minimal",
                         company=None, location=None, description=None, url=None,
                         contract_type=None, salary_text=None)
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([longue, sans_rien])])
    run_scan(db, trigger="manuel")

    offre_longue = db.query(Offer).filter(Offer.source_id == "long1").one()
    assert len(offre_longue.title) == 300
    assert len(offre_longue.company) == 200
    assert len(offre_longue.location) == 200
    assert len(offre_longue.contract_type) == 60
    assert len(offre_longue.salary_text) == 200

    offre_vide = db.query(Offer).filter(Offer.source_id == "vide1").one()
    assert offre_vide.company == ""
    assert offre_vide.location == ""
    assert offre_vide.description == ""
    assert offre_vide.url == ""
    assert offre_vide.contract_type == ""
    assert offre_vide.salary_text == ""


def test_hors_ligne_a_la_limite_exacte_de_15_jours(db, monkeypatch):
    """`last_seen_at < cutoff` avec `cutoff = now - 15 jours` : pile 15 jours
    reste en ligne, un instant de plus bascule — la frontière exacte compte.
    Horloge figée (sinon le temps réel écoulé entre les deux calculs rend
    l'égalité pile 15 jours impossible à obtenir de façon fiable)."""
    instant_fixe = local_now()
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer(source_id="lim")])])
    run_scan(db, trigger="manuel")
    offre = db.query(Offer).one()
    offre.last_seen_at = instant_fixe - timedelta(days=15)
    db.commit()

    monkeypatch.setattr(scan_module, "local_now", lambda: instant_fixe)
    autre = _offer(source_id="autre-source", title="QA Engineer")
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([autre])])
    run_scan(db, trigger="manuel")
    db.expire_all()
    offre = db.query(Offer).filter(Offer.source_id == "lim").one()
    assert offre.still_online is True, "pile 15 jours : pas encore hors-ligne"

    offre.last_seen_at = instant_fixe - timedelta(days=15, seconds=1)
    db.commit()
    run_scan(db, trigger="manuel")
    db.expire_all()
    offre = db.query(Offer).filter(Offer.source_id == "lim").one()
    assert offre.still_online is False, "un instant après 15 jours : hors-ligne"


def test_candidat_ia_dont_le_score_egale_le_seuil_est_bien_inclus(db, monkeypatch):
    """`Offer.score >= ai_min_rule_score` : le seuil lui-même doit être retenu,
    pas seulement ce qui est strictement au-dessus."""
    from app.config import settings

    offre = Offer(fingerprint="fp-seuil", source="fake", source_id="seuil",
                  title="Test Manager", company="ACME",
                  score=float(settings.ai_min_rule_score), ai_score=None)
    db.add(offre)
    db.commit()
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([])])
    monkeypatch.setattr(scan_module, "cli_available", lambda: True)
    monkeypatch.setattr(scan_module, "ai_score_offer", lambda offer_dict, cv_text: (90.0, "ok"))
    run_scan(db, trigger="manuel")
    db.expire_all()
    assert db.query(Offer).filter(Offer.source_id == "seuil").one().ai_score == 90.0


def test_budget_ia_a_la_limite_exacte_ne_coupe_pas_encore(db, monkeypatch):
    """`elapsed > AI_BUDGET_SECONDES` strict : à la limite pile, l'affinage
    continue encore — ce n'est que l'instant suivant qui coupe."""
    offres = [_offer(source_id="b1", title="Test Manager", company="Alpha")]
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector(offres)])
    monkeypatch.setattr(scan_module, "cli_available", lambda: True)
    monkeypatch.setattr(scan_module, "ai_score_offer", lambda offer_dict, cv_text: (88.0, "raison"))
    horloge = iter([0.0, float(scan_module.AI_BUDGET_SECONDES)])
    monkeypatch.setattr(scan_module.time, "monotonic", lambda: next(horloge))
    run_scan(db, trigger="manuel")
    assert db.query(Offer).one().ai_score == 88.0, "à la limite exacte, l'offre doit être affinée"


def test_affinage_ia_compte_un_par_offre_pas_deux(db, monkeypatch):
    offres = [_offer(source_id="c1", title="Test Manager", company="Alpha")]
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector(offres)])
    monkeypatch.setattr(scan_module, "cli_available", lambda: True)
    monkeypatch.setattr(scan_module, "ai_score_offer", lambda offer_dict, cv_text: (88.0, "raison"))
    run = run_scan(db, trigger="manuel")
    assert run.source_stats["_ia"]["refined"] == 1


def test_aucune_entree_ia_dans_les_stats_si_rien_naffine(db, monkeypatch):
    """`if ai_refined:` : pas d'offre affinée (CLI absente) => pas d'entrée
    `_ia` fantôme dans les stats, même avec `ai_refined` initialisé à 0."""
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    run = run_scan(db, trigger="manuel")
    assert "_ia" not in run.source_stats


def test_source_desactivee_ne_fausse_pas_les_totaux_du_scan(db, monkeypatch):
    """Une source désactivée n'a ni `new` ni `seen` dans ses stats : le total
    doit retomber sur le défaut 0 de `.get()`, pas planter ni fausser le compte."""
    profil = db.get(Profile, 1)
    profil.sources_enabled = {"inactive": False}
    db.commit()
    inactive = FakeConnector([])
    inactive.name = "inactive"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()]), inactive])
    run = run_scan(db, trigger="manuel")
    assert run.new_count == 1
    assert run.seen_count == 0


def test_run_full_scan_sans_envoi_demail_ne_renvoie_jamais_true(db, monkeypatch):
    import app.services.digest as digest_module

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [FakeConnector([_offer()])])
    monkeypatch.setattr(
        digest_module, "send_digest_email",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ne doit pas être appelé")),
    )
    _, _, envoye = run_full_scan(db, trigger="manuel", send_email=False)
    assert envoye is False


def test_rescore_all_recalcule_chaque_offre_et_compte_juste(db):
    profil = db.get(Profile, 1)
    db.add_all([
        Offer(fingerprint="fp-r1", source="fake", source_id="r1", title="Test Manager",
             company="ACME", description="Selenium, Jira, pilotage QA.", score=0),
        Offer(fingerprint="fp-r2", source="fake", source_id="r2", title="QA Engineer",
             company="Beta", description="Cypress, automatisation.", score=0),
    ])
    db.commit()
    compte = rescore_all(db)
    assert compte == 2
    scores = [o.score for o in db.query(Offer).all()]
    assert all(s > 0 for s in scores)


def test_budget_ia_vaut_bien_20_minutes(db):
    """`AI_BUDGET_SECONDES = 20 * 60` : les tests de budget vérifient tous un
    comportement RELATIF à cette constante — aucun ne prouve sa valeur réelle,
    documentée dans le commentaire du module (marge sous l'heure Windows)."""
    assert scan_module.AI_BUDGET_SECONDES == 1200


def test_entreprise_de_trois_lettres_indexee_pendant_le_scan_meme_pour_une_offre_toute_neuve(db, monkeypatch):
    """`if len(new_key) >= 3` (scan.py:~280) : une offre tout juste créée dans
    CE scan doit être indexée par entreprise pour que l'offre suivante — même
    scan, autre source — puisse la retrouver par titre proche. Index déjà
    couvert à la frontière pour les offres PRÉEXISTANTES (voir
    `test_index_offres_connues_...`) ; ici, pour une offre née pendant le scan."""
    premiere = RawOffer(source="fake1", source_id="n1", title="Test Manager Senior",
                        company="EDF", url="https://un.com/1")  # "edf" normalisé = 3 caractères
    fake1 = FakeConnector([premiere])
    fake1.name = "fake1"
    seconde = RawOffer(source="fake2", source_id="n2", title="Test Manager Senior H/F",
                       company="EDF", url="https://deux.com/2")
    fake2 = FakeConnector([seconde])
    fake2.name = "fake2"

    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [fake1, fake2])
    run_scan(db, trigger="manuel")

    assert db.query(Offer).count() == 1, "fusionnées dans le même scan grâce à l'index entreprise"


def test_source_desactivee_ne_fausse_pas_le_balayage_hors_ligne(db, monkeypatch):
    """Régression : une source désactivée n'a pas de clé `fetched` dans ses
    stats (`{"label": ..., "skipped": True}`) — elle ne doit jamais être
    comptée parmi les sources qui ont balayé le marché (scan.py:~294).
    Ne tue PAS, en pratique, le littéral `s.get("fetched", 0)` : ce défaut
    est gardé avant par `not s.get("skipped")`, toujours faux ici — les deux
    conditions ne sont jamais évaluées côté droit pour une source
    désactivée. Vérifié par mutation manuelle (Sprint 61) : le défaut `0`
    de ce `.get()` est un mutant équivalent — aucune entrée de `stats` qui
    passe le garde `skipped` n'est jamais dépourvue de la clé `fetched`
    (toujours posée avant le fetch, ligne 202)."""
    ancienne = Offer(fingerprint="fp-skip", source="desactivee", source_id="skip1",
                     title="Test Manager", company="ACME", final_score=50,
                     still_online=True, last_seen_at=local_now() - timedelta(days=30))
    db.add(ancienne)
    profil = db.get(Profile, 1)
    profil.sources_enabled = {"desactivee": False}
    db.commit()

    desactivee = FakeConnector([])
    desactivee.name = "desactivee"
    monkeypatch.setattr(scan_module, "ALL_CONNECTORS", [desactivee])
    run_scan(db, trigger="manuel")
    db.expire_all()
    assert db.query(Offer).one().still_online is True, (
        "une source désactivée n'a rien balayé : elle ne doit jamais rendre une offre hors-ligne"
    )
