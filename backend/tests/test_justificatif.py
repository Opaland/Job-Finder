"""Sprint 29 : justificatif de recherche d'emploi (France Travail)."""
from datetime import date, datetime, timedelta

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


# --- Sprint 61 : trous relevés par mutation testing --------------------------
#
# Beaucoup des survivants de `scripts/mutation.py justificatif` portent sur la
# MISE EN PAGE du PDF (marges, tailles de police, positions en mm, longueurs
# de troncature d'affichage, seuil de saut de page) : du pur cosmétique, sans
# effet sur l'exactitude du document. Les traquer exigerait des assertions sur
# les coordonnées de dessin — fragile et hors de proportion avec l'enjeu (un
# justificatif légèrement mal aligné n'est pas une donnée fausse). Seuls les
# trous qui touchent au CONTENU (fenêtre de dates, repli entreprise, comptage
# des démarches) sont traités ici.

def test_entreprise_manquante_affiche_un_libelle_par_defaut(db):
    offer = Offer(
        fingerprint="fp-sansent", source="france_travail", source_id="sansent",
        title="Test Manager", company="", final_score=85.0, status="postulee",
        status_history=[{"status": "postulee", "date": local_now().isoformat(), "par": "utilisateur"}],
    )
    db.add(offer)
    db.commit()
    aujourdhui = local_now().date()
    actes = actes_de_recherche(db, aujourdhui - timedelta(days=1), aujourdhui)
    assert actes[0]["entreprise"] == "Entreprise non précisée"


def test_entretien_fiche_a_la_limite_exacte_de_la_periode_est_compte(db):
    """`debut <= quand <= fin` : un entretien daté PILE au début ou à la fin
    de la période ne doit pas être exclu — les deux bornes sont inclusives."""
    depuis = date(2026, 1, 5)
    jusqu_a = date(2026, 1, 20)
    debut_exact = datetime.combine(depuis, datetime.min.time())
    fin_exacte = datetime.combine(jusqu_a, datetime.max.time())
    offer = Offer(
        fingerprint="fp-bornes", source="manuelle", source_id="bornes",
        title="Test Manager", company="ACME", final_score=85.0,
        interviews=[
            {"date": debut_exact.isoformat(), "format": "Visio"},
            {"date": fin_exacte.isoformat(), "format": "Sur site"},
        ],
    )
    db.add(offer)
    db.commit()
    actes = actes_de_recherche(db, depuis, jusqu_a)
    assert len(actes) == 2


def test_acte_de_statut_a_la_limite_exacte_de_la_periode_est_compte(db):
    """Même frontière inclusive, côté `status_history` cette fois — chemin
    de code distinct (ligne ~53), jamais exercé par le test ci-dessus."""
    depuis = date(2026, 2, 5)
    jusqu_a = date(2026, 2, 20)
    debut_exact = datetime.combine(depuis, datetime.min.time())
    fin_exacte = datetime.combine(jusqu_a, datetime.max.time())
    offer = Offer(
        fingerprint="fp-bornes2", source="manuelle", source_id="bornes2",
        title="Test Manager", company="ACME", final_score=85.0, status="relancee",
        status_history=[
            {"status": "postulee", "date": debut_exact.isoformat(), "par": "utilisateur"},
            {"status": "relancee", "date": fin_exacte.isoformat(), "par": "utilisateur"},
        ],
    )
    db.add(offer)
    db.commit()
    actes = actes_de_recherche(db, depuis, jusqu_a)
    assert len(actes) == 2


# Sprint 61 : le comptage par type de démarche (resume[cle] += 1, lignes
# ~71-76 de justificatif.py) et toute la mise en page du PDF (marges,
# polices, positions en mm, longueurs de troncature d'affichage, seuil de
# saut de page) restent non couverts par mutation testing. Vérifier le
# CONTENU réel du PDF rendu demanderait une extraction de texte (pypdf),
# indisponible dans cet environnement (son backend crypto plante : module
# `_cffi_backend` manquant). Chasser le reste — du pur cosmétique de mise en
# page — serait de toute façon hors de proportion avec l'enjeu : une donnée
# mal comptée serait grave, un alignement en mm imprécis ne l'est pas.
