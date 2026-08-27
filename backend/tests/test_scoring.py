"""Tests du moteur de classement : les offres proches du CV de Cédric doivent scorer haut."""
import json
from pathlib import Path

import pytest

from app.services.cv_parser import extract_skills
from app.services.scoring import combined_score, score_offer

SEED = json.loads(
    (Path(__file__).resolve().parent.parent / "seed" / "profile_seed.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def profile():
    return {
        "target_titles": SEED["target_titles"],
        "skills": extract_skills(SEED["cv_text"]),
        "location_keywords": SEED["location_keywords"],
        "radius_km": SEED["radius_km"],
        "remote_ok": True,
        "contracts": SEED["contracts"],
        "sector_bonus": SEED["sector_bonus"],
        "excluded_keywords": [],
    }


def test_offre_ideale_score_tres_haut(profile):
    """Test Manager santé à Lyon en CDI = le poste qu'il occupe déjà → score très élevé."""
    offer = {
        "title": "Test Manager / QA Lead",
        "company": "Éditeur santé",
        "location": "Lyon (69)",
        "contract_type": "CDI",
        "description": (
            "Éditeur de logiciels de santé (ISO 13485, IEC 62304) recherche un Test Manager "
            "pour piloter une équipe de testeurs : stratégie de test risk-based testing, "
            "automatisation Selenium et Playwright, tests API avec KarateDSL et REST Assured, "
            "CI/CD GitLab, Jira, Squash TM, management d'équipe, pilotage des releases."
        ),
        "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score >= 85, result.breakdown


def test_offre_qa_junior_plafonnee(profile):
    offer = {
        "title": "Testeur QA junior",
        "company": "ESN",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Testeur débutant, tests manuels, Jira.",
        "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score <= 30


def test_offre_hors_qa_plafonnee(profile):
    offer = {
        "title": "Développeur PHP Symfony",
        "company": "Agence web",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Développement backend PHP, MySQL, déploiement continu.",
        "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score <= 20


def test_remote_compense_la_distance(profile):
    offer_paris = {
        "title": "QA Lead",
        "company": "Scale-up",
        "location": "Paris",
        "contract_type": "CDI",
        "description": "Pilotage QA, automatisation Cypress, management.",
        "remote": False,
    }
    offer_remote = dict(offer_paris, remote=True, description="Full remote. " + offer_paris["description"])
    score_paris = score_offer(offer_paris, profile).score
    score_remote = score_offer(offer_remote, profile).score
    assert score_remote > score_paris


def test_offre_lyon_mieux_classee_que_region(profile):
    base = {
        "title": "Test Manager",
        "company": "X",
        "contract_type": "CDI",
        "description": "Management de l'équipe QA, stratégie de test.",
        "remote": False,
    }
    lyon = score_offer(dict(base, location="Villeurbanne (69)"), profile).score
    grenoble = score_offer(dict(base, location="Grenoble (38)"), profile).score
    assert lyon > grenoble


def test_mot_cle_exclu_plafonne(profile):
    profile = dict(profile, excluded_keywords=["sopra steria"])
    offer = {
        "title": "Test Manager",
        "company": "Sopra Steria",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Poste chez Sopra Steria : pilotage QA.",
        "remote": False,
    }
    assert score_offer(offer, profile).score <= 10


def test_mot_cle_exclu_sur_le_nom_d_entreprise_seul(profile):
    """L'exclusion s'applique même si l'entreprise n'est citée que dans son champ."""
    profile = dict(profile, excluded_keywords=["capgemini"])
    offer = {
        "title": "Test Manager",
        "company": "Capgemini",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Pilotage QA, management, Selenium.",  # le nom n'y figure pas
        "remote": False,
    }
    assert score_offer(offer, profile).score <= 10


def test_breakdown_explicable(profile):
    offer = {
        "title": "QA Engineer",
        "company": "Start-up",
        "location": "Lyon",
        "contract_type": "CDI",
        "description": "Automatisation Playwright, CI/CD, Jira.",
        "remote": False,
    }
    result = score_offer(offer, profile)
    labels = [b["label"] for b in result.breakdown]
    assert "Adéquation du poste" in labels
    assert "Compétences du CV" in labels
    assert "Localisation" in labels
    assert all("detail" in b for b in result.breakdown)


def test_combined_score():
    assert combined_score(80, None) == 80
    assert combined_score(80, 60) == 70
    assert combined_score(50.5, 49.5) == 50.0


# ---------------------------------------------------------------------------
# Le barème, critère par critère.
#
# Les tests ci-dessus sont directionnels (« l'offre idéale score haut ») : ils
# ne remarquent pas qu'un palier a bougé de 40 à 41, ni qu'un `and` est devenu
# un `or`. Le test de mutation (scripts/mutation.py) l'a chiffré : 19 % des
# fautes injectées dans scoring.py passaient inaperçues. Ceux-ci tiennent le
# barème documenté en tête de scoring.py, palier par palier.
# ---------------------------------------------------------------------------

from app.services.scoring import (  # noqa: E402
    DEFAULT_WEIGHTS, _contract_score, _location_score, _sector_score,
    _seniority_score, _skills_score, _title_score,
)


class TestBaremeTitre:
    """0 à 40 points — le critère qui pèse le plus lourd."""

    def test_metier_exerce_vaut_le_maximum(self):
        assert _title_score("test manager h/f", "", [])[0] == 40

    def test_un_titre_vise_du_profil_vaut_aussi_le_maximum(self):
        assert _title_score("architecte qualite", "", ["Architecte qualité"])[0] == 40

    def test_metier_proche_vaut_26(self):
        assert _title_score("qa engineer", "", [])[0] == 26

    def test_titre_qa_sans_management_vaut_16(self):
        assert _title_score("charge de recette", "", [])[0] == 16

    def test_qa_seulement_dans_la_description_vaut_6(self):
        assert _title_score("chef de projet", "pilotage de la recette et des tests", [])[0] == 6

    def test_hors_qa_vaut_zero(self):
        assert _title_score("developpeur php", "symfony, mysql", [])[0] == 0

    def test_les_paliers_sont_strictement_decroissants(self):
        paliers = [
            _title_score("test manager", "", [])[0],
            _title_score("qa engineer", "", [])[0],
            _title_score("charge de recette", "", [])[0],
            _title_score("chef de projet", "recette", [])[0],
            _title_score("developpeur php", "", [])[0],
        ]
        assert paliers == sorted(paliers, reverse=True) and len(set(paliers)) == 5


class TestBaremeSeniorite:
    """0 à 10 points, et le drapeau « junior » qui déclenche un plafond."""

    def test_junior_vaut_zero_et_leve_le_drapeau(self):
        points, _, junior = _seniority_score("testeur junior", "")
        assert points == 0 and junior is True

    def test_deux_indices_de_management_valent_10(self):
        points, _, junior = _seniority_score("test manager", "management d'une equipe")
        assert points == 10 and junior is False

    def test_un_seul_indice_de_management_vaut_7(self):
        assert _seniority_score("responsable", "pilotage du projet")[0] == 7

    def test_senior_sans_management_vaut_aussi_7(self):
        assert _seniority_score("testeur senior", "tests manuels")[0] == 7

    def test_niveau_non_precise_vaut_4(self):
        assert _seniority_score("testeur", "tests manuels")[0] == 4

    def test_exactement_deux_indices_suffisent_pour_les_10_points(self):
        """La bascule est à 2 indices : avec un seul, on retombe à 7."""
        deux = _seniority_score("responsable qualite", "gouvernance et roadmap qualite")
        un = _seniority_score("responsable qualite", "roadmap qualite")
        assert deux[0] == 10 and un[0] == 7

    def test_un_poste_non_junior_ne_leve_jamais_le_drapeau(self):
        """Le drapeau déclenche un plafond à 30 : il ne doit pas se lever à tort."""
        for titre, description in [("responsable", "pilotage"), ("testeur senior", ""),
                                   ("testeur", "tests manuels")]:
            assert _seniority_score(titre, description)[2] is False, titre

    def test_junior_l_emporte_sur_le_management(self):
        """Un « manager junior » reste junior : le plafond doit tomber."""
        points, _, junior = _seniority_score("manager junior", "management d'une equipe")
        assert points == 0 and junior is True


class TestBaremeLocalisation:
    """0 à 15 points. L'ordre des cas compte autant que les valeurs."""

    def test_zone_de_recherche_vaut_15(self):
        assert _location_score("lyon", "", "", ["Lyon"], True, False)[0] == 15

    def test_teletravail_complet_vaut_13(self):
        assert _location_score("paris", "", "", ["Lyon"], True, True)[0] == 13

    def test_teletravail_ignore_si_l_utilisateur_n_en_veut_pas(self):
        assert _location_score("paris", "", "", ["Lyon"], False, True)[0] != 13

    def test_region_vaut_8(self):
        assert _location_score("grenoble (38)", "", "", ["Lyon"], True, False)[0] == 8

    def test_teletravail_partiel_hors_zone_vaut_6(self):
        assert _location_score("paris", "teletravail partiel", "", ["Lyon"], True, False)[0] == 6

    def test_localisation_absente_vaut_5(self):
        assert _location_score("", "", "", ["Lyon"], True, False)[0] == 5

    def test_hors_zone_sans_teletravail_vaut_1(self):
        assert _location_score("bordeaux", "", "", ["Lyon"], True, False)[0] == 1

    def test_la_zone_l_emporte_sur_le_teletravail(self):
        assert _location_score("lyon", "full remote", "", ["Lyon"], True, True)[0] == 15


class TestBaremeContratSecteurCompetences:

    def test_cdi_recherche_vaut_5(self):
        assert _contract_score("cdi", "", ["CDI"])[0] == 5

    def test_cdi_non_recherche_ne_vaut_pas_5(self):
        assert _contract_score("cdi", "", ["Freelance"])[0] != 5

    def test_freelance_recherche_vaut_5(self):
        assert _contract_score("freelance", "", ["Freelance / portage"])[0] == 5

    def test_cdd_vaut_2(self):
        assert _contract_score("cdd", "", ["CDI"])[0] == 2

    def test_contrat_non_precise_vaut_3_donc_mieux_qu_un_cdd(self):
        assert _contract_score("", "", ["CDI"])[0] == 3 > _contract_score("cdd", "", ["CDI"])[0]

    def test_le_freelance_ne_rapporte_que_s_il_est_recherche(self):
        """Symétrique du CDI : une mission freelance non voulue n'est pas un plus."""
        assert _contract_score("freelance", "", ["CDI"])[0] != 5
        assert _contract_score("mission de portage", "", ["Freelance"])[0] == 5

    def test_secteur_connu_vaut_5_sinon_2(self):
        assert _sector_score("editeur de logiciels sante", ["santé"])[0] == 5
        assert _sector_score("agence de voyage", ["santé"])[0] == 2

    def test_aucune_competence_citee_vaut_zero(self):
        assert _skills_score("aucun rapport", "poste", ["selenium", "jira"])[0] == 0

    def test_rendement_decroissant_plafonne_a_25(self):
        une = _skills_score("selenium", "", ["selenium", "jira", "cypress"])[0]
        trois = _skills_score("selenium jira cypress", "", ["selenium", "jira", "cypress"])[0]
        assert 0 < une < trois <= 25
        outils = [f"outil{i}" for i in range(12)]
        assert _skills_score(" ".join(outils), "", outils)[0] == 25


class TestPlafonds:
    """Des valeurs exactes, pas des « à peu près »."""

    def _offre(self, **champs):
        base = {"title": "Test Manager", "company": "ACME", "location": "Lyon",
                "contract_type": "CDI", "remote": False,
                "description": "Management de l'equipe QA, strategie de test, Selenium, Jira, CI/CD."}
        base.update(champs)
        return base

    def test_hors_qa_plafonne_exactement_a_20(self, profile):
        resultat = score_offer(self._offre(title="Developpeur PHP",
                                           description="Symfony, MySQL, Docker."), profile)
        assert resultat.score == 20
        assert any("hors QA" in b["detail"] for b in resultat.breakdown)

    def test_junior_plafonne_exactement_a_30(self, profile):
        resultat = score_offer(self._offre(title="Test Manager junior"), profile)
        assert resultat.score == 30
        assert any("junior" in b["detail"] for b in resultat.breakdown)

    def test_mot_exclu_plafonne_exactement_a_10(self, profile):
        assert score_offer(self._offre(), dict(profile, excluded_keywords=["acme"])).score == 10

    def test_le_mot_exclu_l_emporte_sur_les_autres_plafonds(self):
        profil = {"target_titles": [], "skills": [], "location_keywords": ["Lyon"],
                  "remote_ok": True, "contracts": ["CDI"], "sector_bonus": [],
                  "excluded_keywords": ["acme"]}
        assert score_offer(self._offre(title="Test Manager junior"), profil).score == 10


class TestPonderations:

    def test_le_detail_somme_toujours_au_score(self, profile):
        """Promesse de l'interface : le détail explique le score entier."""
        offre = {"title": "QA Engineer", "company": "X", "location": "Lyon",
                 "contract_type": "CDI", "description": "Selenium, Jira.", "remote": False}
        resultat = score_offer(offre, profile)
        assert round(sum(b["points"] for b in resultat.breakdown), 1) == resultat.score

    def test_le_total_des_parts_fait_toujours_100(self, profile):
        offre = {"title": "Test Manager", "company": "X", "location": "Lyon",
                 "contract_type": "CDI", "description": "Management, Selenium.", "remote": False}
        for poids in ({}, {"titre": 80, "competences": 10}, {k: 1 for k in DEFAULT_WEIGHTS}):
            resultat = score_offer(offre, dict(profile, scoring_weights=poids))
            assert round(sum(b["max"] for b in resultat.breakdown if b["max"])) == 100, poids

    def test_une_ponderation_a_zero_annule_le_critere(self, profile):
        profil = dict(profile, scoring_weights={"titre": 40, "competences": 25, "seniorite": 10,
                                                "localisation": 0, "contrat": 5, "secteur": 5})
        offre = {"title": "Test Manager", "company": "X", "contract_type": "CDI",
                 "description": "Management, strategie de test.", "remote": False}
        assert (score_offer(dict(offre, location="Lyon"), profil).score
                == score_offer(dict(offre, location="Bordeaux"), profil).score)

    def test_le_teletravail_est_accepte_par_defaut(self, profile):
        """Un profil qui ne dit rien sur le télétravail ne doit pas le refuser."""
        sans_mention = {k: v for k, v in profile.items() if k != "remote_ok"}
        offre = {"title": "Test Manager", "company": "X", "location": "Paris",
                 "contract_type": "CDI", "description": "Management.", "remote": True}
        detail = [b for b in score_offer(offre, sans_mention).breakdown
                  if b["label"] == "Localisation"][0]
        assert "télétravail complet" in detail["detail"]

    def test_un_mot_exclu_vide_ne_plafonne_rien(self, profile):
        """Une ligne blanche dans la liste des mots exclus ne doit pas tout plafonner."""
        profil = dict(profile, excluded_keywords=["", "   ", "entreprise-a-eviter"])
        offre = {"title": "Test Manager", "company": "ACME", "location": "Lyon",
                 "contract_type": "CDI", "description": "Management, Selenium.", "remote": False}
        assert score_offer(offre, profil).score > 10

    def test_le_detail_somme_au_score_meme_sur_une_offre_plafonnee(self, profile):
        """Les lignes « Plafond » sont explicatives : elles ne pèsent rien."""
        offre = {"title": "Developpeur PHP", "company": "X", "location": "Lyon",
                 "contract_type": "CDI", "description": "Symfony, MySQL.", "remote": False}
        resultat = score_offer(offre, profile)
        plafonds = [b for b in resultat.breakdown if b["label"] == "Plafond"]
        assert plafonds and all(b["points"] == 0 for b in plafonds)
        assert resultat.score == 20

    def test_des_ponderations_toutes_nulles_ne_font_pas_planter(self, profile):
        profil = dict(profile, scoring_weights={k: 0 for k in DEFAULT_WEIGHTS})
        offre = {"title": "Test Manager", "company": "X", "location": "Lyon",
                 "contract_type": "CDI", "description": "Management.", "remote": False}
        assert score_offer(offre, profil).score == 0
