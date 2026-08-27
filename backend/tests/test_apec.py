"""Connecteur APEC — défauts constatés sur l'API réelle le 27/08/2026.

Ces défauts étaient invisibles sans vrais appels : ils ne font pas échouer le
scan, ils le font réussir avec des données fausses.

Les tests portent sur le CHEMIN DE CODE, pas sur les constantes du module :
ré-affirmer `DEPARTEMENTS_LYON == [...]` ne prouve rien, puisque le payload
pourrait très bien ne plus s'en servir.
"""
import pytest

from app.connectors.apec import CONTRATS_APEC, ApecConnector

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

PROFIL = {"search_queries": ["test manager"]}


# --- Ce qu'on envoie à l'APEC ------------------------------------------------

def test_la_recherche_lyonnaise_filtre_par_departement():
    """Régression df71b55 : `distance` fait répondre 500, et
    `pointGeolocDeReference` seul est ignoré — une recherche « Lyon » renvoyait
    Nantes, Saran et Annemasse (1 offre sur 20 dans le Rhône).

    `payloads()` est une fonction pure : on lit la vraie requête, sans réseau et
    sans faux client. Que l'APEC l'accepte vraiment est vérifié pour de bon
    dans test_sources_reelles.py."""
    lyonnais = ApecConnector.payloads(PROFIL)[0]
    assert set(lyonnais["lieux"]) == {"69", "01", "38", "42"}
    assert "distance" not in lyonnais
    assert "pointGeolocDeReference" not in lyonnais


def test_la_recherche_teletravail_reste_nationale():
    """Le télétravail n'a pas de département : la brider sur Lyon reviendrait à
    supprimer la seule jambe du scan qui ramène des offres hors du Rhône."""
    national = ApecConnector.payloads(PROFIL)[-1]
    assert "lieux" not in national
    assert "télétravail" in national["motsCles"]


def test_chaque_requete_de_recherche_porte_un_mot_cle_du_profil():
    """Un profil sans requête retomberait sur les mots-clés par défaut ; on
    vérifie surtout qu'aucune requête ne part à vide."""
    requetes = ApecConnector.payloads({"search_queries": ["test manager", "QA"]})
    assert [r["motsCles"] for r in requetes] == [
        "test manager", "QA", "test manager télétravail",
    ]


# --- Ce qu'on lit dans la réponse -------------------------------------------

def test_les_champs_essentiels_sont_mappes():
    offre = ApecConnector()._parse(OFFRE_REELLE)
    assert offre.source_id == "178970208W"
    assert offre.title == "Lead test - Secteur monétique F/H"
    assert offre.company == "O2MAX"
    assert offre.location == "Lyon 01 - 69"
    assert offre.salary_text == "40 - 45 k€ brut annuel"


def test_le_lien_de_l_offre_n_est_pas_un_404():
    """Régression c60ba8c : la forme au PLURIEL (« recherche-emplois / emplois »)
    renvoie un 404. Chaque offre APEC portait un lien mort — on épingle donc
    l'URL COMPLÈTE produite, pas la constante du module."""
    offre = ApecConnector()._parse(OFFRE_REELLE)
    assert offre.url == (
        "https://www.apec.fr/candidat/recherche-emploi.html"
        "/emploi/detail-offre/178970208W"
    )


def test_le_code_de_contrat_devient_un_libelle():
    """Régression : `typeContrat` vaut 101888, pas « CDI ». Injecté tel quel,
    le scoring n'y voyait pas un CDI et donnait 2 points au lieu de 5."""
    assert ApecConnector()._parse(OFFRE_REELLE).contract_type == "CDI"


def test_le_code_cdd_reste_un_cdd():
    """Les deux codes doivent se distinguer : les confondre transformerait
    silencieusement tous les CDD en CDI dans le tableau de bord."""
    offre = ApecConnector()._parse({**OFFRE_REELLE, "typeContrat": 101887})
    assert offre.contract_type == "CDD"
    assert CONTRATS_APEC["101887"] != CONTRATS_APEC["101888"]


@pytest.mark.parametrize("code", [597137, 597139])
def test_les_codes_d_alternance_sont_reconnus(code):
    """Relevé sur ~600 offres lyonnaises : 25 intitulés sur 26 en 597137 et 3
    sur 3 en 597139 disent « en alternance ». Laissés inconnus, ils sortaient
    « non précisé » — et le scoring donne PLUS de points à un contrat non
    précisé qu'à un contrat identifié comme différent de la recherche."""
    assert ApecConnector()._parse({**OFFRE_REELLE, "typeContrat": code}).contract_type == "Alternance"


def test_un_code_de_contrat_inconnu_laisse_le_champ_vide():
    """« Non précisé » est plus juste qu'un numéro affiché à l'utilisateur."""
    assert ApecConnector()._parse({**OFFRE_REELLE, "typeContrat": 999999}).contract_type == ""


def test_un_libelle_deja_textuel_est_conserve():
    """Si l'API se met à renvoyer des libellés, on ne les jette pas."""
    assert ApecConnector()._parse({**OFFRE_REELLE, "typeContrat": "CDD"}).contract_type == "CDD"


def test_la_date_de_publication_est_lue():
    """Régression : `datePublication` était ignorée — toutes les offres
    paraissaient publiées à l'instant, et le tri par fraîcheur ne triait rien."""
    offre = ApecConnector()._parse(OFFRE_REELLE)
    assert offre.published_at is not None
    assert offre.published_at.strftime("%Y-%m-%d") == "2026-08-04"
    assert offre.published_at.tzinfo is None      # heures naïves partout


def test_une_publication_de_fin_de_soiree_reste_au_bon_jour():
    """L'APEC répond en UTC (« +0000 »). Retirer le fuseau sans CONVERTIR
    datait de la veille toute offre publiée après 22 h — et la déplaçait donc
    dans le tri « les plus récentes »."""
    offre = ApecConnector()._parse(
        {**OFFRE_REELLE, "datePublication": "2026-08-04T23:38:14.000+0000"}
    )
    assert offre.published_at.strftime("%Y-%m-%d %H:%M") == "2026-08-05 01:38"


def test_une_offre_sans_date_de_publication_utilise_la_validation():
    sans_publication = {k: v for k, v in OFFRE_REELLE.items() if k != "datePublication"}
    offre = ApecConnector()._parse(
        {**sans_publication, "dateValidation": "2026-07-01T10:00:00.000+0000"}
    )
    assert offre.published_at.strftime("%Y-%m-%d") == "2026-07-01"


def test_une_offre_sans_titre_est_ignoree():
    assert ApecConnector()._parse({**OFFRE_REELLE, "intitule": ""}) is None
