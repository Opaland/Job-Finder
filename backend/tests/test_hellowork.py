"""Parsing des pages HelloWork, sur une VRAIE page capturée.

Le connecteur lit du HTML sans classes sémantiques : c'est le genre de code qui
casse en silence quand le site évolue. La fixture est un extrait réel figé par
`python -m app.cli sources --brut` — le jour où HelloWork change sa structure,
ces tests tombent au lieu de laisser passer des offres à moitié vides.

Historique : le parseur s'arrêtait au div le plus interne de la carte. Résultat
mesuré sur cette même page — lieu vide sur 4 offres sur 4, contrat absent,
date de publication absente, description de 35 caractères.
"""
from pathlib import Path

import pytest

from app.connectors.hellowork import HelloWorkConnector

PAGE = (Path(__file__).resolve().parent / "fixtures" / "hellowork_recherche.html").read_text(
    encoding="utf-8"
)


@pytest.fixture(scope="module")
def offres():
    return HelloWorkConnector()._parse_page(PAGE)


def test_toutes_les_offres_de_la_page_sont_extraites(offres):
    assert len(offres) == 4


def test_aucun_champ_essentiel_n_est_vide(offres):
    """C'est exactement ce que le diagnostic appelle une source « suspecte »."""
    for offre in offres:
        for champ in ("title", "company", "location", "url", "source_id"):
            assert (getattr(offre, champ) or "").strip(), f"{champ} vide sur « {offre.title} »"


def test_le_titre_ne_contient_pas_le_nom_de_l_entreprise(offres):
    """Régression : le titre sortait en « Test Manager H/F Stormshield »."""
    for offre in offres:
        assert offre.company not in offre.title, offre.title


def test_les_lieux_sont_bien_du_bassin_lyonnais(offres):
    """La recherche portait sur Lyon : le lieu doit être extrait, pas deviné."""
    assert [o.location for o in offres] == [
        "Lyon 9e - 69", "Lyon - 69", "Lyon - 69", "Lyon - 69",
    ]


def test_le_contrat_est_reconnu(offres):
    assert [o.contract_type for o in offres] == ["CDI", "CDI", "CDI", "Indépendant"]


def test_le_teletravail_partiel_ne_compte_pas_pour_du_complet(offres):
    """Le scoring accorde 13 points sur 15 au télétravail complet : compter un
    « Télétravail partiel » gonflerait toutes les offres lyonnaises."""
    assert all(o.remote is False for o in offres)


def test_la_date_de_publication_est_extraite(offres):
    """« il y a 13 jours » → une vraie date, sinon l'offre paraît toujours fraîche."""
    assert all(o.published_at is not None for o in offres)
    # La plus ancienne des quatre a bien été publiée avant la plus récente.
    dates = [o.published_at for o in offres]
    assert min(dates) < max(dates)


def test_l_url_est_absolue_et_pointe_sur_l_offre(offres):
    for offre in offres:
        assert offre.url.startswith("https://www.hellowork.com/fr-fr/emplois/")
        assert offre.source_id in offre.url


def test_une_page_sans_offre_ne_leve_pas(offres):
    assert HelloWorkConnector()._parse_page("<html><body>rien</body></html>") == []
