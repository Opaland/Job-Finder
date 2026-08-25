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
