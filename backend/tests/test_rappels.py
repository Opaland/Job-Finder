"""Sprint 35 : rappel de la veille (entretien ou action datée prévus demain)."""
from datetime import timedelta

from app.models import Offer, local_now
from app.services.rappels import echeances_de_demain, rappel_html


def _offre(db, source_id="r1", **kw):
    offer = Offer(fingerprint=f"fp-{source_id}", source="apec", source_id=source_id,
                  title="Test Manager", company="Éditeur santé", url="https://exemple.fr",
                  final_score=90.0, **kw)
    db.add(offer)
    db.commit()
    return offer


def test_entretien_de_demain_repere(client, db):
    demain = (local_now() + timedelta(days=1)).replace(hour=14, minute=30, second=0, microsecond=0)
    _offre(db, interviews=[{"date": demain.isoformat(), "format": "Visio", "interlocuteur": "Claire"}])

    echeances = echeances_de_demain(db)
    assert len(echeances["entretiens"]) == 1
    entretien = echeances["entretiens"][0]
    assert entretien["heure"] == "14:30"
    assert entretien["interlocuteur"] == "Claire"
    assert entretien["fiche_prete"] is False      # aucune fiche générée


def test_fiche_preparee_signalee(client, db):
    demain = (local_now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    _offre(db, interview_prep="Pitch, points forts…",
           interviews=[{"date": demain.isoformat(), "format": "Sur site"}])
    assert echeances_de_demain(db)["entretiens"][0]["fiche_prete"] is True


def test_aujourdhui_et_apres_demain_ignores(client, db):
    aujourdhui = local_now().replace(hour=11, minute=0, second=0, microsecond=0)
    apres_demain = (local_now() + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)
    _offre(db, source_id="r2", interviews=[
        {"date": aujourdhui.isoformat()}, {"date": apres_demain.isoformat()},
    ])
    echeances = echeances_de_demain(db)
    assert echeances["entretiens"] == []


def test_action_datee_de_demain(client, db):
    demain = (local_now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    _offre(db, next_action_date=demain, next_action_note="Relancer Claire")
    echeances = echeances_de_demain(db)
    assert len(echeances["actions"]) == 1
    assert echeances["actions"][0]["note"] == "Relancer Claire"


def test_entretiens_tries_par_heure(client, db):
    base = (local_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    _offre(db, interviews=[
        {"date": base.replace(hour=16, minute=0).isoformat()},
        {"date": base.replace(hour=9, minute=15).isoformat()},
    ])
    heures = [e["heure"] for e in echeances_de_demain(db)["entretiens"]]
    assert heures == ["09:15", "16:00"]


def test_email_mentionne_la_fiche_manquante(client, db):
    demain = (local_now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    _offre(db, interviews=[{"date": demain.isoformat(), "format": "Visio"}])
    html = rappel_html(echeances_de_demain(db))
    assert "Éditeur santé" in html
    assert "fiche de préparation non générée" in html


def test_route_de_test_sans_smtp(client, db):
    """Sans SMTP configuré, la route répond quand même avec le contenu prévu."""
    demain = (local_now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    _offre(db, interviews=[{"date": demain.isoformat()}])
    resp = client.post("/api/digests/reminder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["envoye"] is False          # pas de SMTP dans les tests
    assert len(data["entretiens"]) == 1
