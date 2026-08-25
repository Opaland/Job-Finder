"""Sprint 21 : entretiens datés rattachés à une offre."""
from datetime import timedelta

from app.models import Offer, local_now
from app.services.digest import next_interviews


def _offre(db, **kw):
    offer = Offer(fingerprint="fp-entretien", source="manuelle", source_id="e1",
                  title="Test Manager", company="Éditeur santé", final_score=90.0, **kw)
    db.add(offer)
    db.commit()
    return offer


def test_ajout_et_suppression_d_un_entretien(client, db):
    offer = _offre(db)
    quand = (local_now() + timedelta(days=3)).replace(microsecond=0)

    resp = client.post(f"/api/offers/{offer.id}/interviews", json={
        "date": quand.isoformat(), "format": "Visio", "interlocuteur": "Claire Dupont",
    })
    assert resp.status_code == 201, resp.text
    entretiens = resp.json()["interviews"]
    assert len(entretiens) == 1
    assert entretiens[0]["interlocuteur"] == "Claire Dupont"
    assert entretiens[0]["format"] == "Visio"

    resp = client.delete(f"/api/offers/{offer.id}/interviews/0")
    assert resp.status_code == 200
    assert resp.json()["interviews"] == []


def test_entretiens_tries_par_date(client, db):
    offer = _offre(db)
    tard = (local_now() + timedelta(days=10)).replace(microsecond=0)
    tot = (local_now() + timedelta(days=2)).replace(microsecond=0)
    client.post(f"/api/offers/{offer.id}/interviews", json={"date": tard.isoformat()})
    client.post(f"/api/offers/{offer.id}/interviews", json={"date": tot.isoformat()})
    dates = [e["date"] for e in client.get(f"/api/offers/{offer.id}").json()["interviews"]]
    assert dates == sorted(dates)


def test_suppression_index_invalide(client, db):
    offer = _offre(db)
    assert client.delete(f"/api/offers/{offer.id}/interviews/5").status_code == 404


def test_prochains_entretiens_du_digest(client, db):
    offer = _offre(db)
    passe = (local_now() - timedelta(days=5)).replace(microsecond=0)
    futur = (local_now() + timedelta(days=4)).replace(microsecond=0)
    lointain = (local_now() + timedelta(days=60)).replace(microsecond=0)
    for quand in (passe, futur, lointain):
        client.post(f"/api/offers/{offer.id}/interviews", json={"date": quand.isoformat()})

    a_venir = next_interviews(db)
    # Seul l'entretien dans la fenêtre des 21 jours est proposé.
    assert len(a_venir) == 1
    assert a_venir[0]["title"] == "Test Manager"
    assert a_venir[0]["aujourdhui"] is False


def test_compte_rendu_et_relance_planifiee(client, db):
    """Sprint 22 : le compte-rendu se sauvegarde et cale la prochaine action."""
    offer = _offre(db)
    quand = (local_now() - timedelta(days=1)).replace(microsecond=0)
    client.post(f"/api/offers/{offer.id}/interviews", json={"date": quand.isoformat()})

    relance = (local_now() + timedelta(days=8)).replace(microsecond=0, second=0)
    resp = client.patch(f"/api/offers/{offer.id}/interviews/0", json={
        "compte_rendu": "Entretien RH puis technique, bonne écoute.",
        "ressenti": "bon",
        "suite": "retour sous 8 jours",
        "relance_le": relance.isoformat(),
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["interviews"][0]["ressenti"] == "bon"
    assert "bonne écoute" in data["interviews"][0]["compte_rendu"]
    # La suite annoncée devient une action datée, avec une note explicite.
    assert data["next_action_date"].startswith(relance.strftime("%Y-%m-%d"))
    assert "retour sous 8 jours" in data["next_action_note"]


def test_compte_rendu_partiel_ne_touche_pas_le_reste(client, db):
    offer = _offre(db)
    quand = (local_now() - timedelta(days=2)).replace(microsecond=0)
    client.post(f"/api/offers/{offer.id}/interviews",
                json={"date": quand.isoformat(), "interlocuteur": "Claire"})
    client.patch(f"/api/offers/{offer.id}/interviews/0", json={"ressenti": "mitige"})
    entretien = client.get(f"/api/offers/{offer.id}").json()["interviews"][0]
    assert entretien["ressenti"] == "mitige"
    assert entretien["interlocuteur"] == "Claire"   # non écrasé
    assert entretien["compte_rendu"] == ""


def test_compte_rendu_entretien_inexistant(client, db):
    offer = _offre(db)
    assert client.patch(f"/api/offers/{offer.id}/interviews/3", json={"ressenti": "bon"}).status_code == 404
