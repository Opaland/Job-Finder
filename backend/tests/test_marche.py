"""Sprint 25 : compétences les plus demandées par le marché."""
from app.models import Offer, Profile
from app.services.marche import competences_demandees


def _offre(db, id_source, titre, description):
    db.add(Offer(fingerprint=f"fp-{id_source}", source="manuelle", source_id=id_source,
                 title=titre, company="ACME", description=description, final_score=70.0))
    db.commit()


def test_classement_des_competences(client, db):
    _offre(db, "m1", "QA Lead", "Automatisation Selenium et Playwright, CI/CD GitLab.")
    _offre(db, "m2", "Test Manager", "Stratégie de test, Selenium, Jira.")
    _offre(db, "m3", "Testeur", "Tests manuels avec Jira.")

    resultat = competences_demandees(db)
    assert resultat["total_offres"] == 3
    assert resultat["assez_de_donnees"] is True
    classement = {c["competence"]: c for c in resultat["competences"]}
    assert classement["selenium"]["offres"] == 2
    assert classement["jira"]["offres"] == 2
    assert classement["playwright"]["offres"] == 1
    # Le classement est trié par nombre d'offres décroissant.
    nombres = [c["offres"] for c in resultat["competences"]]
    assert nombres == sorted(nombres, reverse=True)


def test_part_en_pourcentage(client, db):
    _offre(db, "m1", "QA", "Selenium partout.")
    _offre(db, "m2", "QA", "Rien de particulier.")
    selenium = next(c for c in competences_demandees(db)["competences"] if c["competence"] == "selenium")
    assert selenium["part"] == 50


def test_competences_du_cv_reperees(client, db):
    profile = db.get(Profile, 1)
    profile.skills = ["selenium", "jira"]
    db.commit()
    _offre(db, "m1", "QA Lead", "Selenium, Playwright et Jira.")

    resultat = competences_demandees(db)
    classement = {c["competence"]: c for c in resultat["competences"]}
    assert classement["selenium"]["dans_le_cv"] is True
    assert classement["playwright"]["dans_le_cv"] is False
    # Les manquantes sont exactement celles absentes du CV.
    assert "playwright" in [c["competence"] for c in resultat["manquantes"]]
    assert "selenium" not in [c["competence"] for c in resultat["manquantes"]]


def test_base_vide_ne_casse_pas(client, db):
    resultat = competences_demandees(db)
    assert resultat["total_offres"] == 0
    assert resultat["assez_de_donnees"] is False
    assert resultat["competences"] == []


def test_route_api(client, db):
    _offre(db, "m1", "QA Lead", "Playwright et Cypress.")
    resp = client.get("/api/market/skills?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["competences"]) <= 5


# --- Sprint 26 : salaires et entreprises ------------------------------------

def test_lecture_des_salaires_formats_reels():
    from app.services.marche import montants_annuels
    assert montants_annuels("45 000 - 55 000 € / an") == [45000, 55000]
    assert montants_annuels("45K€ à 60K€") == [45000, 60000]
    assert montants_annuels("Mensuel de 3500,00 Euros à 4200,00 Euros") == [42000, 50400]
    assert montants_annuels("Selon profil") == []
    assert montants_annuels("2 ans d'expérience") == []   # aucune unité monétaire


def test_montants_aberrants_ecartes():
    from app.services.marche import montants_annuels
    assert montants_annuels("1 200 € par an") == []        # sous le plancher
    assert montants_annuels("900 000 € / an") == []        # au-dessus du plafond


def test_qui_recrute_et_mediane(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    for i, (entreprise, salaire, score) in enumerate([
        ("ACME", "45 000 - 55 000 € / an", 80.0),
        ("ACME", "50 000 € / an", 70.0),
        ("Bêta", "", 60.0),
    ]):
        db.add(Offer(fingerprint=f"fp-s{i}", source="manuelle", source_id=f"s{i}",
                     title="Test Manager", company=entreprise, salary_text=salaire, final_score=score))
    db.commit()

    resultat = qui_recrute(db)
    premiere = resultat["entreprises"][0]
    assert premiere["entreprise"] == "ACME"
    assert premiere["offres"] == 2
    assert premiere["score_moyen"] == 75.0
    assert resultat["offres_avec_salaire"] == 2
    salaires = resultat["salaires"][0]
    assert salaires["minimum"] == 45000 and salaires["maximum"] == 55000
    assert salaires["median"] == 50000


def test_entreprise_vide_regroupee(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add(Offer(fingerprint="fp-x", source="manuelle", source_id="x", title="QA", company="", final_score=50.0))
    db.commit()
    assert qui_recrute(db)["entreprises"][0]["entreprise"] == "Entreprise non précisée"


# --- Sprint 27 : manques récurrents repérés par l'IA ------------------------

def test_manques_recurrents(client, db):
    from app.models import Offer, Profile
    from app.services.marche import manques_recurrents
    profile = db.get(Profile, 1)
    profile.skills = ["selenium"]
    db.commit()
    for i, analyse in enumerate([
        "Le CV couvre Selenium mais Playwright et k6 manquent.",
        "Il faudrait ajouter Playwright pour ce poste.",
        None,
    ]):
        db.add(Offer(fingerprint=f"fp-g{i}", source="manuelle", source_id=f"g{i}",
                     title="QA", company="ACME", final_score=70.0, gap_analysis=analyse))
    db.commit()

    resultat = manques_recurrents(db)
    assert resultat["analyses"] == 2                    # l'offre sans analyse est ignorée
    manques = {m["competence"]: m["citee_dans"] for m in resultat["manques"]}
    assert manques["playwright"] == 2
    assert manques["k6"] == 1
    assert "selenium" not in manques                    # déjà au CV : pas un manque


# --- Sprint 28 : fraîcheur et annonces fantômes -----------------------------

def test_tranches_de_fraicheur_et_fantomes(client, db):
    from datetime import timedelta

    from app.models import Offer, local_now
    from app.services.marche import fraicheur
    maintenant = local_now()
    cas = [
        ("f1", maintenant - timedelta(days=2), True, "nouvelle"),
        ("f2", maintenant - timedelta(days=20), True, "vue"),
        ("f3", maintenant - timedelta(days=45), True, "nouvelle"),
        ("f4", maintenant - timedelta(days=120), True, "nouvelle"),   # fantôme
        ("f5", maintenant - timedelta(days=200), False, "nouvelle"),  # ancienne mais hors ligne
        ("f6", None, True, "nouvelle"),
        ("f7", maintenant - timedelta(days=300), True, "refusee"),    # close : ignorée
    ]
    for source_id, publiee, en_ligne, statut in cas:
        db.add(Offer(fingerprint=f"fp-{source_id}", source="manuelle", source_id=source_id,
                     title="QA", company="ACME", final_score=60.0,
                     published_at=publiee, still_online=en_ligne, status=statut))
    db.commit()

    resultat = fraicheur(db)
    tranches = {t["tranche"]: t["offres"] for t in resultat["tranches"]}
    assert tranches["0-7"] == 1
    assert tranches["8-30"] == 1
    assert tranches["31-60"] == 1
    assert tranches["60+"] == 2          # f4 et f5
    assert tranches["inconnue"] == 1
    # Seule une offre ancienne ET toujours en ligne est signalée fantôme.
    fantomes = [f["source_id"] if "source_id" in f else f["jours"] for f in resultat["fantomes"]]
    assert len(resultat["fantomes"]) == 1
    assert resultat["fantomes"][0]["jours"] >= 120
