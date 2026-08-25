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
