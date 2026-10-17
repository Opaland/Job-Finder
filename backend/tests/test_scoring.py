"""Tests du moteur de classement : les offres proches du CV de Cédric doivent scorer haut."""
import json
from pathlib import Path

import pytest

from app.services.cv_parser import extract_skills
from app.services.scoring import (
    ScoreResult, _contract_score, _location_score, _seniority_score, _skills_score,
    combined_score, score_offer,
)

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


# --- Sprint 60 : trous relevés par mutation testing (scripts/mutation.py) ---

def test_score_result_arrondit_les_points_a_une_decimale():
    res = ScoreResult()
    res.add("Test", 8.3333333, 25, "detail")
    assert res.breakdown[0]["points"] == 8.3


def test_description_pile_a_50_caracteres_n_est_plus_trop_courte():
    """_DESCRIPTION_TROP_COURTE = 50 : le seuil est strict (<), 50 caractères
    pile doivent être jugés normalement, pas excusés comme « trop courte »."""
    desc = "x" * 50
    points, detail = _skills_score(desc, "", ["playwright"])
    assert "trop courte" not in detail
    assert "Aucune compétence" in detail

    desc_49 = "x" * 49
    _, detail_49 = _skills_score(desc_49, "", ["playwright"])
    assert "trop courte" in detail_49


def test_skills_score_formule_exacte_sous_le_plafond():
    """Avec peu de compétences, le plafond de 25 ne joue pas : la formule
    elle-même (25 * sqrt(n) / 3) doit être exacte, pas seulement son plafond."""
    points, _ = _skills_score("playwright", "", ["playwright"])
    assert points == pytest.approx(25.0 * 1 ** 0.5 / 3.0, rel=1e-9)


def test_skills_score_plafonne_a_25():
    beaucoup = [f"competence{i}" for i in range(15)]
    desc = " ".join(beaucoup)
    points, _ = _skills_score(desc, "", beaucoup)
    assert points == 25.0


def test_skills_score_tronque_l_affichage_a_8_competences():
    huit = [f"competence{i}" for i in range(8)]
    neuf = huit + ["competence9z"]
    _, detail_8 = _skills_score(" ".join(huit), "", huit)
    _, detail_9 = _skills_score(" ".join(neuf), "", neuf)
    assert "…" not in detail_8
    assert "…" in detail_9
    # La 9e compétence ne doit pas apparaître dans la liste affichée (hits[:8]).
    assert "competence9z" not in detail_9
    assert all(f"competence{i}" in detail_9 for i in range(8))


def test_skills_score_zero_sans_match_et_description_suffisante():
    points, detail = _skills_score("x" * 100, "", ["playwright"])
    assert points == 0
    assert "Aucune compétence" in detail


def test_location_score_remote_nu_sans_full_ni_complet_reste_partiel():
    """REMOTE_HINTS[:6] exclut volontairement le mot nu « remote »/« teletravail »
    (sans « full »/« complet »/« total ») — sinon toute mention vague de remote
    vaudrait les 13 pts du full remote plutôt que les 6 pts du partiel."""
    points, detail = _location_score(
        location_norm="", desc_norm="remote possible", title_norm="",
        location_keywords=[], remote_ok=True, remote_flag=False,
    )
    assert points == 6
    assert "partiel" in detail


def test_location_score_hors_zone_sans_remote_vaut_1():
    points, detail = _location_score(
        location_norm="paris", desc_norm="", title_norm="",
        location_keywords=["lyon"], remote_ok=True, remote_flag=False,
    )
    assert points == 1
    assert "hors de ta zone" in detail


def test_contract_score_freelance_matche_par_sous_chaine_du_profil():
    """Le `or` qui laisse matcher soit une valeur exacte du profil (ex.
    « freelance / portage ») soit toute valeur qui CONTIENT « freelance »
    (ex. « mission freelance ») — ici seul le second cas est vrai."""
    points, detail = _contract_score("freelance", "", ["mission freelance"])
    assert points == 5
    assert "freelance" in detail.lower()


def test_contract_score_cdd_interim_vaut_2():
    points, _ = _contract_score("cdd", "", [])
    assert points == 2


def test_contract_score_type_different_non_vide_vaut_2():
    """Contrat précisé mais hors CDI/freelance/CDD/intérim (ex. vacation) :
    pas la même branche que « non précisé », même valeur de points."""
    points, detail = _contract_score("vacation", "", [])
    assert points == 2
    assert "différent de ta recherche" in detail


def test_seniority_score_non_precise_vaut_4():
    points, detail, is_junior = _seniority_score("testeur fonctionnel", "")
    assert points == 4
    assert is_junior is False
    assert "non précisé" in detail


def test_sector_score_affichage_tronque_a_4_secteurs():
    from app.services.scoring import _sector_score

    secteurs = ["sante", "banque", "retail", "assurance", "energie"]
    texte = " ".join(secteurs)
    points, detail = _sector_score(texte, secteurs)
    assert points == 5
    assert "energie" not in detail
    assert all(s in detail for s in secteurs[:4])


def test_poids_tous_a_zero_ne_plante_pas(profile):
    """`total_weight = sum(weights.values()) or 1` : si l'utilisateur mettait
    toutes les pondérations à 0 (réglage aberrant mais saisissable), il ne
    doit pas y avoir de division par zéro — juste un score à 0."""
    profile = dict(profile, scoring_weights={k: 0 for k in
                   ("titre", "competences", "seniorite", "localisation", "contrat", "secteur")})
    offer = {
        "title": "Test Manager", "company": "X", "location": "Lyon",
        "contract_type": "CDI", "description": "Pilotage QA.", "remote": False,
    }
    result = score_offer(offer, profile)
    assert result.score == 0.0


def test_plafond_junior_affiche_a_zero_point_et_zero_max(profile):
    offer_junior = {
        "title": "Testeur QA junior", "company": "ESN", "location": "Lyon",
        "contract_type": "CDI", "description": "Stage, tests manuels.", "remote": False,
    }
    result = score_offer(offer_junior, profile)
    plafond = next(b for b in result.breakdown if b["label"] == "Plafond")
    assert plafond["points"] == 0 and plafond["max"] == 0
    assert "30" in plafond["detail"]


def test_plafonds_affiches_a_zero_point_et_zero_max(profile):
    offer_hors_qa = {
        "title": "Développeur PHP", "company": "X", "location": "Lyon",
        "contract_type": "CDI", "description": "PHP, MySQL.", "remote": False,
    }
    result = score_offer(offer_hors_qa, profile)
    plafond = next(b for b in result.breakdown if b["label"] == "Plafond")
    assert plafond["points"] == 0 and plafond["max"] == 0

    profile_exclu = dict(profile, excluded_keywords=["acme corp"])
    offer_exclu = {
        "title": "Test Manager", "company": "Acme Corp", "location": "Lyon",
        "contract_type": "CDI", "description": "Pilotage QA.", "remote": False,
    }
    result_exclu = score_offer(offer_exclu, profile_exclu)
    exclu = next(b for b in result_exclu.breakdown if b["label"] == "Mot-clé exclu")
    assert exclu["points"] == 0 and exclu["max"] == 0


def test_salaire_pile_au_minimum_ne_declenche_pas_le_signal(profile):
    """Le seuil est strict (<) : un salaire affiché pile égal au minimum
    souhaité n'est pas « sous » ce minimum — ne doit pas être signalé."""
    profile = dict(profile, min_salary=45000)
    offer = {
        "title": "Test Manager", "company": "X", "location": "Lyon",
        "contract_type": "CDI", "description": "Pilotage QA.", "remote": False,
        "salary_text": "45 000 € / an",
    }
    result = score_offer(offer, profile)
    assert not any(b["label"] == "Salaire" for b in result.breakdown)


def test_part_des_criteres_arrondie_a_une_decimale(profile):
    """`round(share, 1)` (champ "max" du breakdown) : des pondérations qui ne
    tombent pas rond doivent être arrondies à une décimale, pas deux."""
    profile = dict(profile, scoring_weights={
        "titre": 1, "competences": 1, "seniorite": 1,
        "localisation": 1, "contrat": 1, "secteur": 1,
    })
    offer = {
        "title": "Test Manager", "company": "X", "location": "Lyon",
        "contract_type": "CDI", "description": "Pilotage QA.", "remote": False,
    }
    result = score_offer(offer, profile)
    titre = next(b for b in result.breakdown if b["label"] == "Adéquation du poste")
    assert titre["max"] == 16.7  # 100/6 arrondi à une décimale, pas 16.67


def test_combined_score_arrondit_a_une_decimale_pas_deux():
    assert combined_score(80.3333, None) == 80.3
    assert combined_score(80.11, 60.12) == round((80.11 + 60.12) / 2, 1)


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

    def test_titre_au_pluriel_est_reconnu(self):
        """Issue #1 : contains_word ne matchait que le singulier — un titre
        français au pluriel (très courant) passait à tort pour hors QA/test.
        Cas réel mesuré sur le marché (09/09/2026) : plafonné à 0/40 avant
        correction, alors que « Qualité & Tests » est un indice QA générique."""
        assert _title_score("pilote de la demarche qualite tests - assurance h/f", "", [])[0] == 16
        assert _title_score("responsable tests", "", [])[0] == 40        # CORE_TITLES : "responsable test"
        assert _title_score("ingenieur de tests h/f", "", [])[0] == 26   # NEAR_TITLES : "ingenieur test"

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

    def test_interim_vaut_2_comme_le_cdd(self):
        """Branche jamais isolée (mutation testée : `or` → `and` traversait la
        suite entière, "interim" seul tombant par coïncidence sur le même
        score que le cas générique)."""
        points, detail = _contract_score("interim", "", ["CDI"])
        assert points == 2
        assert "CDD/intérim" in detail

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


class TestSignalSalaire:
    """min_salary (issue #4) : signalé dans le détail, jamais pénalisant —
    une fourchette affichée est souvent négociable."""

    def _offre(self, salary_text="", **champs):
        base = {"title": "Test Manager", "company": "ACME", "location": "Lyon",
                "contract_type": "CDI", "remote": False, "salary_text": salary_text,
                "description": "Management de l'equipe QA, strategie de test, Selenium, Jira, CI/CD."}
        base.update(champs)
        return base

    def test_salaire_sous_le_minimum_est_signale(self, profile):
        resultat = score_offer(self._offre(salary_text="35 000 - 40 000 € / an"),
                                dict(profile, min_salary=50000))
        detail = next((b for b in resultat.breakdown if b["label"] == "Salaire"), None)
        assert detail is not None
        assert "35 000" not in detail["detail"]   # c'est la borne HAUTE (40 000) qui compte
        assert "40 000" in detail["detail"] and "50 000" in detail["detail"]
        assert detail["points"] == 0 and detail["max"] == 0   # informatif, pas un plafond

    def test_salaire_au_dessus_du_minimum_n_est_pas_signale(self, profile):
        resultat = score_offer(self._offre(salary_text="55 000 - 60 000 € / an"),
                                dict(profile, min_salary=50000))
        assert not any(b["label"] == "Salaire" for b in resultat.breakdown)

    def test_salaire_non_precise_n_est_pas_signale(self, profile):
        """L'absence de salaire (la majorité des offres) n'est pas un signal négatif."""
        resultat = score_offer(self._offre(salary_text=""), dict(profile, min_salary=50000))
        assert not any(b["label"] == "Salaire" for b in resultat.breakdown)

    def test_sans_min_salary_rien_n_est_signale(self, profile):
        resultat = score_offer(self._offre(salary_text="20 000 € / an"), dict(profile, min_salary=None))
        assert not any(b["label"] == "Salaire" for b in resultat.breakdown)

    def test_le_signal_salaire_ne_change_jamais_le_score(self, profile):
        """Vérifié directement : avec/sans le signal, le score numérique est identique."""
        offre = self._offre(salary_text="10 000 € / an")
        avec = score_offer(offre, dict(profile, min_salary=90000)).score
        sans = score_offer(offre, dict(profile, min_salary=None)).score
        assert avec == sans


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
        """Un profil qui ne dit rien sur le télétravail ne doit pas le refuser.

        Assertion resserrée (mutation testée) : `"télétravail complet" in
        detail` passait aussi bien sur le texte d'ÉCHEC du même critère
        ("...sans télétravail complet.") — la mutation `remote_ok=True` par
        défaut → `False` traversait les 52 tests du fichier sans échouer.
        """
        sans_mention = {k: v for k, v in profile.items() if k != "remote_ok"}
        offre = {"title": "Test Manager", "company": "X", "location": "Paris",
                 "contract_type": "CDI", "description": "Management.", "remote": True}
        detail = [b for b in score_offer(offre, sans_mention).breakdown
                  if b["label"] == "Localisation"][0]
        assert detail["detail"].startswith("Poste en télétravail complet")
        assert detail["points"] == 13          # pondérations par défaut (pas de scoring_weights)

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
