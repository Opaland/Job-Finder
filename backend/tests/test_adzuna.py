"""Connecteur Adzuna : parsing défensif face à des champs explicitement null."""
from app.connectors.adzuna import AdzunaConnector


def test_titre_null_ne_plante_pas():
    """Issue #36 : item.get("title", "") ne protège que la clé ABSENTE — une
    clé présente mais à `null` (vu en pratique côté Adzuna) renvoyait quand
    même None, et .replace() levait une AttributeError qui faisait perdre
    TOUTE la page de résultats, pas seulement cette offre."""
    offre = AdzunaConnector()._parse({
        "id": "1", "title": None, "company": {"display_name": "Acme"},
        "location": {"display_name": "Lyon"}, "description": None,
    })
    assert offre.title == ""
    assert offre.company == "Acme"
    assert offre.description == ""


def test_company_et_location_absentes_ne_plantent_pas():
    offre = AdzunaConnector()._parse({"id": "2", "title": "QA Lead"})
    assert offre.company == ""
    assert offre.location == ""


def test_titre_normal_toujours_nettoye_des_balises():
    offre = AdzunaConnector()._parse({"id": "3", "title": "<strong>QA</strong> Lead"})
    assert offre.title == "QA Lead"
