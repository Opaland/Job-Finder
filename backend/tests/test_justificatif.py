"""Sprint 29 : justificatif de recherche d'emploi (France Travail)."""
from datetime import timedelta

from app.models import Offer, Profile, local_now
from app.services.justificatif import actes_de_recherche


def _offre_postulee(db, source_id, jours_avant, entreprise="ACME"):
    quand = local_now() - timedelta(days=jours_avant)
    offer = Offer(
        fingerprint=f"fp-{source_id}", source="france_travail", source_id=source_id,
        title="Test Manager", company=entreprise, final_score=85.0, status="postulee",
        status_history=[
            {"status": "nouvelle", "date": (quand - timedelta(days=1)).isoformat(), "par": "scan"},
            {"status": "postulee", "date": quand.isoformat(), "par": "utilisateur"},
        ],
    )
    db.add(offer)
    db.commit()
    return offer


def test_actes_sur_la_periode(client, db):
    _offre_postulee(db, "j1", 5)
    _offre_postulee(db, "j2", 40)          # hors période
    aujourdhui = local_now().date()
    actes = actes_de_recherche(db, aujourdhui - timedelta(days=30), aujourdhui)
    assert len(actes) == 1
    assert actes[0]["acte"] == "Candidature envoyée"
    assert actes[0]["poste"] == "Test Manager"


def test_relances_et_entretiens_comptes(client, db):
    offer = _offre_postulee(db, "j3", 10)
    historique = list(offer.status_history)
    historique.append({"status": "relancee", "date": (local_now() - timedelta(days=3)).isoformat(), "par": "utilisateur"})
    offer.status_history = historique
    offer.interviews = [{"date": (local_now() - timedelta(days=1)).isoformat(), "format": "Visio"}]
    db.commit()

    aujourdhui = local_now().date()
    actes = actes_de_recherche(db, aujourdhui - timedelta(days=30), aujourdhui)
    libelles = [a["acte"] for a in actes]
    assert "Candidature envoyée" in libelles
    assert "Relance" in libelles
    assert "Entretien (Visio)" in libelles
    # Le plus récent d'abord.
    assert actes[0]["date"] >= actes[-1]["date"]


def test_pdf_genere_et_telechargeable(client, db):
    profile = db.get(Profile, 1)
    profile.full_name, profile.email = "Cédric Moretti", "ced.moretti@gmail.com"
    db.commit()
    _offre_postulee(db, "j4", 2, entreprise="Éditeur santé")

    resp = client.get("/api/exports/justificatif.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "justificatif_recherche_" in resp.headers["content-disposition"]


def test_periode_vide_reste_valide(client, db):
    resp = client.get("/api/exports/justificatif.pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_dates_incoherentes_refusees(client, db):
    resp = client.get("/api/exports/justificatif.pdf?depuis=2026-08-01&jusqu_a=2026-07-01")
    assert resp.status_code == 400
    assert "précéder" in resp.json()["detail"]


def test_entretien_declare_par_le_statut_seul_est_compte(client, db):
    """France Travail veut la liste des démarches : un entretien noté uniquement
    par un changement de statut ne doit pas manquer au justificatif."""
    offer = _offre_postulee(db, "j5", 8)
    historique = list(offer.status_history)
    historique.append({"status": "entretien", "date": (local_now() - timedelta(days=2)).isoformat(),
                       "par": "utilisateur"})
    offer.status_history = historique
    db.commit()

    aujourdhui = local_now().date()
    actes = actes_de_recherche(db, aujourdhui - timedelta(days=30), aujourdhui)
    assert [a["acte"] for a in actes].count("Entretien") == 1


def test_un_entretien_fiche_n_est_pas_compte_deux_fois(client, db):
    """Statut « entretien » + entretien fiché le même jour = un seul acte."""
    offer = _offre_postulee(db, "j6", 8)
    quand = local_now() - timedelta(days=2)
    historique = list(offer.status_history)
    historique.append({"status": "entretien", "date": quand.isoformat(), "par": "utilisateur"})
    offer.status_history = historique
    offer.interviews = [{"date": quand.isoformat(), "format": "Visio"}]
    db.commit()

    aujourdhui = local_now().date()
    actes = actes_de_recherche(db, aujourdhui - timedelta(days=30), aujourdhui)
    entretiens = [a["acte"] for a in actes if a["acte"].startswith("Entretien")]
    assert entretiens == ["Entretien (Visio)"]
