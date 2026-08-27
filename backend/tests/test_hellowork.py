"""Parsing des pages HelloWork, sur une VRAIE page capturée.

Le connecteur lit du HTML sans classes sémantiques : c'est le genre de code qui
casse en silence quand le site évolue. La fixture est un extrait réel figé par
`python -m app.cli sources --brut` — le jour où HelloWork change sa structure,
ces tests tombent au lieu de laisser passer des offres à moitié vides.

Historique : le parseur s'arrêtait au div le plus interne de la carte. Résultat
mesuré sur cette même page — lieu vide sur 4 offres sur 4, contrat absent,
date de publication absente, description de 35 caractères. Depuis, les champs
sont lus dans l'`aria-label` du lien ; la lecture positionnelle reste en repli
et garde donc ses propres tests.
"""
from pathlib import Path

import pytest

from app.connectors.hellowork import HelloWorkConnector
from app.models import local_now

PAGE = (Path(__file__).resolve().parent / "fixtures" / "hellowork_recherche.html").read_text(
    encoding="utf-8"
)


def page_synthetique(aria=None, textes=(), href="/fr-fr/emplois/12345678.html", liens=1):
    """Carte HelloWork minimale — pour les cas absents de la page réelle."""
    etiquette = f' aria-label="{aria}"' if aria else ""
    ancres = "".join(
        f'<a href="{href}"{etiquette if i == 0 else ""}>Voir l\'offre</a>'
        for i in range(liens)
    )
    contenu = "".join(f"<span>{t}</span>" for t in textes)
    return f"<html><body><ul><li><article>{ancres}{contenu}</article></li></ul></body></html>"


@pytest.fixture(scope="module")
def offres():
    return HelloWorkConnector()._parse_page(PAGE)


# --- Ce que la vraie page doit produire, champ par champ ---------------------

def test_toutes_les_offres_de_la_page_sont_extraites(offres):
    assert len(offres) == 4


def test_les_titres_extraits_sont_exacts(offres):
    """Épinglé et non « non vide » : un badge d'interface ajouté par le site
    (« Recruteur actif », « Publiée aujourd'hui ») décalait tout, et le titre
    de TOUTES les offres devenait ce badge."""
    assert [o.title for o in offres] == [
        "Test Manager H/F",
        "QA Senior - Test Manager H/F",
        "Test Manager H/F",
        "Testeur - Test Manager - Sénior - Lyon H/F",
    ]


def test_les_entreprises_extraites_sont_exactes(offres):
    assert [o.company for o in offres] == ["Stormshield", "Lùkla", "CGI", "Visian"]


def test_les_lieux_sont_bien_du_bassin_lyonnais(offres):
    """La recherche portait sur Lyon : le lieu doit être extrait, pas deviné."""
    assert [o.location for o in offres] == [
        "Lyon 9e - 69", "Lyon - 69", "Lyon - 69", "Lyon - 69",
    ]


def test_le_contrat_est_reconnu(offres):
    assert [o.contract_type for o in offres] == ["CDI", "CDI", "CDI", "Indépendant"]


def test_la_description_resume_les_faits_de_la_carte(offres):
    """La page de résultats n'a pas de description : ce résumé est ce que le
    scoring lit en attendant l'enrichissement. Vidé, il ne se voit pas."""
    assert offres[0].description == "CDI · Lyon 9e - 69"
    assert offres[3].description == "Indépendant · Lyon - 69"


def test_le_titre_ne_contient_pas_le_nom_de_l_entreprise(offres):
    """Régression : le titre sortait en « Test Manager H/F Stormshield »."""
    for offre in offres:
        assert offre.company not in offre.title, offre.title


def test_l_url_est_absolue_et_pointe_sur_l_offre(offres):
    for offre in offres:
        assert offre.url.startswith("https://www.hellowork.com/fr-fr/emplois/")
        assert offre.source_id in offre.url


def test_les_anciennetes_donnent_les_bons_ecarts(offres):
    """« il y a 13 jours » → une vraie date, dans le PASSÉ. Le signe inversé
    laissait `min < max` vrai tout en datant les offres du futur : l'offre la
    plus vieille remontait en tête du tri « les plus récentes »."""
    ages = [round((local_now() - o.published_at).total_seconds() / 86400) for o in offres]
    assert ages == [13, 20, 29, 2]


# --- Les unités de temps -----------------------------------------------------

@pytest.mark.parametrize("mention, jours", [
    ("il y a 3 heures", 0),
    ("il y a 45 minutes", 0),
    ("il y a 1 jour", 1),
    ("il y a 2 semaines", 14),
    ("il y a 3 mois", 90),
    # HelloWork bascule sur cette forme au-delà d'un mois : non reconnue,
    # l'offre perdait sa date et échappait à la détection des annonces fantômes.
    ("plus de 1 mois", 30),
    ("plus de 2 mois", 60),
    ("Aujourd'hui", 0),
    ("Hier", 1),
])
def test_chaque_unite_de_temps_a_sa_valeur(mention, jours):
    """Aplatir les unités (semaine = mois = 1 jour) ne se voit sur aucune page
    dont toutes les offres sont datées en jours — c'est le cas de la fixture."""
    date = HelloWorkConnector._publiee_le([mention])
    assert round((local_now() - date).total_seconds() / 86400) == jours


def test_une_carte_sans_date_ne_bloque_pas():
    assert HelloWorkConnector._publiee_le(["CDI", "Lyon - 69"]) is None


# --- Télétravail : 13 points sur 15 au scoring -------------------------------

def test_le_teletravail_complet_est_marque_remote():
    """Sans ce cas, `_teletravail_complet` pouvait renvoyer `False` en toute
    circonstance sans qu'aucun test ne bronche — et la moitié télétravail du
    scan (deux recherches sur cinq) ne ramenait plus rien d'exploitable."""
    page = page_synthetique(
        "Voir offre de Test Manager H/F à Lyon - 69, chez ACME, "
        "pour un CDI, en temps plein, Télétravail total"
    )
    offre = HelloWorkConnector()._parse_page(page)[0]
    assert offre.remote is True
    assert "Télétravail" in offre.description


@pytest.mark.parametrize("mention", [
    "Télétravail partiel", "Télétravail hybride", "Télétravail 3 jours",
    "Télétravail ponctuel", "Télétravail occasionnel",
])
def test_un_teletravail_partiel_ne_compte_pas_pour_du_complet(mention):
    """Compter un jour par semaine comme du full remote gonflerait le score de
    toutes les offres lyonnaises."""
    page = page_synthetique(
        f"Voir offre de Test Manager H/F à Lyon - 69, chez ACME, "
        f"pour un CDI, en temps plein, {mention}"
    )
    assert HelloWorkConnector()._parse_page(page)[0].remote is False


def test_le_teletravail_sans_accent_est_reconnu():
    """« Teletravail total » dit la même chose que « Télétravail total »."""
    page = page_synthetique(
        "Voir offre de Test Manager H/F à Lyon - 69, chez ACME, "
        "pour un CDI, en temps plein, Teletravail total"
    )
    assert HelloWorkConnector()._parse_page(page)[0].remote is True


def test_le_teletravail_partiel_ne_compte_pas_sur_la_vraie_page(offres):
    assert all(o.remote is False for o in offres)


# --- L'aria-label, source principale -----------------------------------------

def test_un_titre_contenant_a_ne_deborde_pas_sur_le_lieu():
    """« Testeur à Lyon H/F » : c'est le DERNIER « à » qui introduit le lieu."""
    page = page_synthetique(
        "Voir offre de Testeur à Lyon H/F à Villeurbanne - 69, chez ACME, pour un CDI"
    )
    offre = HelloWorkConnector()._parse_page(page)[0]
    assert offre.title == "Testeur à Lyon H/F"
    assert offre.location == "Villeurbanne - 69"


# --- Le repli, si HelloWork retire l'aria-label ------------------------------

def test_sans_aria_label_les_champs_sont_encore_lus():
    page = page_synthetique(textes=[
        "Suivi de candidature", "Test Manager H/F", "Stormshield",
        "Lyon 9e - 69", "CDI", "il y a 4 jours",
    ])
    offre = HelloWorkConnector()._parse_page(page)[0]
    assert offre.title == "Test Manager H/F"
    assert offre.company == "Stormshield"
    assert offre.location == "Lyon 9e - 69"
    assert offre.contract_type == "CDI"


def test_un_salaire_n_est_pas_pris_pour_un_lieu():
    """« 45000 - 60000 € par an » contient un nombre à cinq chiffres : pris pour
    un lieu, l'offre perdait ses 15 points de localisation et sortait du digest."""
    page = page_synthetique(textes=[
        "Test Manager H/F", "Stormshield", "45000 - 60000 € par an",
        "Lyon 9e - 69", "CDI",
    ])
    assert HelloWorkConnector()._parse_page(page)[0].location == "Lyon 9e - 69"


def test_un_code_postal_seul_est_un_lieu():
    """Autre forme observée sur le site. Elle doit occuper tout le texte : un
    « 45000 » perdu dans une fourchette de salaire n'est pas un lieu."""
    page = page_synthetique(textes=[
        "Test Manager H/F", "Stormshield", "69100", "CDI",
    ])
    assert HelloWorkConnector()._parse_page(page)[0].location == "69100"


def test_deux_liens_vers_la_meme_offre_ne_coupent_pas_la_carte():
    """Une carte peut porter le titre ET un bouton « Voir l'offre ». Compter les
    LIENS au lieu des offres arrêtait la remontée au parent immédiat : lieu,
    contrat et date vides sur 100 % des offres."""
    page = page_synthetique(
        textes=["Test Manager H/F", "Stormshield", "Lyon 9e - 69", "CDI"], liens=2,
    )
    offres_page = HelloWorkConnector()._parse_page(page)
    assert offres_page                      # le dédoublonnage est le travail de fetch()
    assert all(o.location == "Lyon 9e - 69" for o in offres_page)


# --- Robustesse --------------------------------------------------------------

def test_aucun_champ_essentiel_n_est_vide(offres):
    """C'est exactement ce que le diagnostic appelle une source « suspecte »."""
    for offre in offres:
        for champ in ("title", "company", "location", "description", "url", "source_id"):
            assert (getattr(offre, champ) or "").strip(), f"{champ} vide sur « {offre.title} »"


def test_une_page_sans_offre_ne_leve_pas():
    assert HelloWorkConnector()._parse_page("<html><body>rien</body></html>") == []


# --- Ce qu'on demande à HelloWork -------------------------------------------

class _ReponsePage:
    def __init__(self, html):
        self.text = html

    def raise_for_status(self):
        return None


class _ClientBidon:
    """Client factice qui retient les URL appelées."""

    def __init__(self, html):
        self.urls = []
        self._html = html

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, **_):
        self.urls.append(url)
        return _ReponsePage(self._html)


def test_le_teletravail_est_un_filtre_pas_un_lieu(monkeypatch):
    """Régression mesurée le 27/08/2026 : « l=Télétravail » répond 200 avec
    « 0 offre ». Deux des cinq recherches ne ramenaient donc jamais rien, et
    aucune erreur ne le signalait — les recherches lyonnaises, elles, marchaient.
    Le filtre dédié « t=Complet » renvoie bien des offres."""
    faux = _ClientBidon(PAGE)
    monkeypatch.setattr(HelloWorkConnector, "client", lambda self: faux)
    HelloWorkConnector().fetch({"search_queries": ["test manager", "qa"]})

    teletravail = [u for u in faux.urls if "t=Complet" in u]
    assert len(teletravail) == 2
    assert not any("l=T%C3%A9l%C3%A9travail" in u for u in faux.urls)
    assert all("&l=" not in u for u in teletravail)


def test_les_recherches_lyonnaises_gardent_le_lieu(monkeypatch):
    faux = _ClientBidon(PAGE)
    monkeypatch.setattr(HelloWorkConnector, "client", lambda self: faux)
    HelloWorkConnector().fetch({"search_queries": ["test manager", "qa", "testeur"]})

    lyonnaises = [u for u in faux.urls if "l=Lyon" in u]
    assert len(lyonnaises) == 3


# --- Le salaire, seul chiffre que HelloWork donne ----------------------------

def test_le_salaire_de_la_carte_est_conserve():
    """`salary_text` restait vide sur 100 % des offres HelloWork alors que la
    carte l'affiche — le scoring n'avait aucun montant à lire."""
    page = page_synthetique(
        "Voir offre de Test Manager H/F à Lyon - 69, chez ACME, pour un CDI",
        textes=["50 000 - 60 000 € / an", "il y a 3 jours"],
    )
    assert HelloWorkConnector()._parse_page(page)[0].salary_text == "50 000 - 60 000 € / an"


def test_une_carte_sans_salaire_laisse_le_champ_vide():
    page = page_synthetique(
        "Voir offre de Test Manager H/F à Lyon - 69, chez ACME, pour un CDI",
        textes=["il y a 3 jours"],
    )
    assert HelloWorkConnector()._parse_page(page)[0].salary_text == ""
