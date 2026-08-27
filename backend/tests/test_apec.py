"""Connecteur APEC — défauts constatés sur l'API réelle le 27/08/2026.

Ces trois défauts étaient invisibles sans vrais appels : ils ne font pas
échouer le scan, ils le font réussir avec des données fausses.
"""
from app.connectors.apec import CONTRATS_APEC, DEPARTEMENTS_LYON, DETAIL_URL, ApecConnector

# Offre réelle, telle que l'API la renvoie (champs conservés à l'identique).
OFFRE_REELLE = {
    "id": 178970208,
    "numeroOffre": "178970208W",
    "intitule": "Lead test - Secteur monétique F/H",
    "nomCommercial": "O2MAX",
    "lieuTexte": "Lyon 01 - 69",
    "salaireTexte": "40 - 45 k€ brut annuel",
    "texteOffre": "Nous recherchons un(e) Lead QA / Test Manager pour accompagner…",
    "datePublication": "2026-08-04T03:38:14.000+0000",
    "typeContrat": 101888,
}


def test_le_lien_de_l_offre_n_est_pas_un_404():
    """Régression : la forme au PLURIEL (« recherche-emplois / emplois »)
    renvoie un 404. Chaque offre APEC portait donc un lien mort."""
    assert "recherche-emploi.html/emploi/detail-offre" in DETAIL_URL
    assert "recherche-emplois" not in DETAIL_URL and "/emplois/" not in DETAIL_URL


def test_le_code_de_contrat_devient_un_libelle():
    """Régression : `typeContrat` vaut 101888, pas « CDI ». Injecté tel quel,
    le scoring n'y voyait pas un CDI et donnait 2 points au lieu de 5."""
    offre = ApecConnector()._parse(OFFRE_REELLE)
    assert offre.contract_type == "CDI"


def test_un_code_de_contrat_inconnu_laisse_le_champ_vide():
    """« Non précisé » est plus juste qu'un numéro affiché à l'utilisateur."""
    offre = ApecConnector()._parse({**OFFRE_REELLE, "typeContrat": 999999})
    assert offre.contract_type == ""


def test_un_libelle_deja_textuel_est_conserve():
    """Si l'API se met à renvoyer des libellés, on ne les jette pas."""
    offre = ApecConnector()._parse({**OFFRE_REELLE, "typeContrat": "CDD"})
    assert offre.contract_type == "CDD"


def test_la_date_de_publication_est_lue():
    """Régression : `datePublication` était ignorée — toutes les offres
    paraissaient publiées à l'instant, et le tri par fraîcheur ne triait rien."""
    offre = ApecConnector()._parse(OFFRE_REELLE)
    assert offre.published_at is not None
    assert offre.published_at.strftime("%Y-%m-%d") == "2026-08-04"
    assert offre.published_at.tzinfo is None      # heures naïves partout


def test_les_champs_essentiels_sont_mappes():
    offre = ApecConnector()._parse(OFFRE_REELLE)
    assert offre.source_id == "178970208W"
    assert offre.title == "Lead test - Secteur monétique F/H"
    assert offre.company == "O2MAX"
    assert offre.location == "Lyon 01 - 69"
    assert offre.salary_text == "40 - 45 k€ brut annuel"
    assert offre.source_id in offre.url


def test_une_offre_sans_titre_est_ignoree():
    assert ApecConnector()._parse({**OFFRE_REELLE, "intitule": ""}) is None


def test_le_filtre_geographique_couvre_le_bassin_lyonnais():
    """L'APEC filtre par département : `distance` fait répondre 500, et
    `pointGeolocDeReference` seul est ignoré (Lyon renvoyait Nantes)."""
    assert "69" in DEPARTEMENTS_LYON
    assert set(DEPARTEMENTS_LYON) <= {"69", "01", "38", "42", "07", "26"}
    assert CONTRATS_APEC["101888"] == "CDI"
