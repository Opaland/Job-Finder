"""Tests des requêtes de scan configurables."""
from app.connectors.base import DEFAULT_QUERIES, profile_queries


def test_defauts_si_rien_configure():
    assert profile_queries({}) == DEFAULT_QUERIES
    assert profile_queries({"search_queries": []}) == DEFAULT_QUERIES
    assert profile_queries({"search_queries": ["  ", ""]}) == DEFAULT_QUERIES


def test_requetes_du_profil_prioritaires():
    profile = {"search_queries": ["test automation", " QA lead "]}
    assert profile_queries(profile) == ["test automation", "QA lead"]


def test_valeurs_non_texte_ignorees():
    profile = {"search_queries": ["QA", 42, None, {"x": 1}]}
    assert profile_queries(profile) == ["QA"]


def test_les_connecteurs_utilisent_les_requetes_du_profil():
    """Les deux connecteurs sans clé construisent leurs recherches depuis le
    profil. `recherches()` et `payloads()` sont des fonctions pures : plus
    besoin de bouchonner un client HTTP pour lire ce qui part."""
    from app.connectors.apec import ApecConnector
    from app.connectors.hellowork import HelloWorkConnector

    profil = {"search_queries": ["automatisation des tests", "QA santé"]}

    urls = [url for _, url in HelloWorkConnector.recherches(profil)]
    assert any("automatisation+des+tests" in u for u in urls)
    assert any("QA+sant" in u for u in urls)
    assert not any("test+manager" in u for u in urls)      # défauts non utilisés

    motscles = [p["motsCles"] for p in ApecConnector.payloads(profil)]
    assert "automatisation des tests" in motscles
    assert "QA santé" in motscles
    assert "test manager" not in motscles
