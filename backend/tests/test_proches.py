"""Issue #43 : signal « offres très proches » — une même mission republiée par
plusieurs intermédiaires (agrégateur affiché comme employeur) n'était signalée
nulle part. Jamais une fusion : find_twin() (services/scan.py) reste seul
responsable du dédoublonnage, test_scan_dedupe.py le couvre séparément.
"""
from app.models import Offer
from app.services.proches import DESCRIPTION_MIN, offres_proches

DESCRIPTION_LONGUE = (
    "Testeur fonctionnel Paiements/SEPA, secteur bancaire, Villeurbanne, 3 jours de "
    "télétravail par semaine, mission longue durée avec montée en compétences prévue."
)


def _offre(db, **champs):
    base = {
        "fingerprint": f"fp-{champs.get('source_id', '1')}", "source": "hellowork",
        "source_id": "1", "title": "Testeur fonctionnel", "company": "Hellowork",
        "final_score": 60.0, "status": "nouvelle", "description": DESCRIPTION_LONGUE,
    }
    base.update(champs)
    db.add(Offer(**base))
    db.commit()


def test_meme_mission_republiee_signalee(db):
    _offre(db, source_id="1", company="Hellowork")
    _offre(db, source_id="2", company="Cadremploi", source="apec")
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    proches = offres_proches(db, cible)

    assert len(proches) == 1
    assert proches[0]["company"] == "Cadremploi"
    assert proches[0]["ratio"] >= 0.85


def test_description_trop_courte_jamais_comparee(db):
    """Deux descriptions HelloWork de 18 caractères ne doivent jamais matcher :
    pas assez de matière pour juger (même logique que _DESCRIPTION_TROP_COURTE)."""
    _offre(db, source_id="1", description="CDI · Lyon - 69")
    _offre(db, source_id="2", description="CDI · Lyon - 69")
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    assert len(cible.description) < DESCRIPTION_MIN
    assert offres_proches(db, cible) == []


def test_offres_distinctes_non_signalees(db):
    _offre(db, source_id="1", description=DESCRIPTION_LONGUE)
    _offre(db, source_id="2", description="Lead QA e-commerce, Paris, management de 5 testeurs, Scrum.")
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    assert offres_proches(db, cible) == []


def test_description_absente_ne_plante_pas(db):
    """APEC tronque parfois sans renvoyer de description du tout (CLAUDE.md) —
    `description=None` ne doit jamais faire planter la comparaison."""
    _offre(db, source_id="1", description=None)
    _offre(db, source_id="2", description=DESCRIPTION_LONGUE)
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    assert offres_proches(db, cible) == []


def test_offre_fermee_ignoree(db):
    """Une offre refusée/fermée ne mérite plus le signal — déjà écartée par l'utilisateur."""
    _offre(db, source_id="1")
    _offre(db, source_id="2", status="refusee")
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    assert offres_proches(db, cible) == []


def test_route_offre_detail_porte_le_signal(client, db):
    _offre(db, source_id="1")
    _offre(db, source_id="2", company="Cadremploi", source="apec")
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    resp = client.get(f"/api/offers/{cible.id}")
    assert resp.status_code == 200
    proches = resp.json()["offres_proches"]
    assert len(proches) == 1
    assert proches[0]["company"] == "Cadremploi"


def test_le_signal_survit_a_un_patch(client, db):
    """Régression (revue Sprint 52) : ouvrir une offre déclenche un PATCH
    (passage « nouvelle » → « vue ») dont la réponse remplace l'offre affichée
    côté frontend — le PATCH doit porter le même signal que le GET, sinon le
    bandeau d'avertissement disparaît dès la première interaction."""
    _offre(db, source_id="1")
    _offre(db, source_id="2", company="Cadremploi", source="apec")
    cible = db.query(Offer).filter(Offer.source_id == "1").one()

    resp = client.patch(f"/api/offers/{cible.id}", json={"status": "vue"})
    assert resp.status_code == 200
    proches = resp.json()["offres_proches"]
    assert len(proches) == 1
    assert proches[0]["company"] == "Cadremploi"
