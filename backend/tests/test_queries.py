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


def test_connecteurs_utilisent_les_requetes(monkeypatch):
    """Le connecteur HelloWork construit ses recherches depuis le profil."""
    from app.connectors.hellowork import HelloWorkConnector

    captured = []

    class FakeResponse:
        status_code = 200
        text = "<html></html>"
        def raise_for_status(self): pass

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, url):
            captured.append(url)
            return FakeResponse()

    connector = HelloWorkConnector()
    monkeypatch.setattr(connector, "client", lambda: FakeClient())
    connector.fetch({"search_queries": ["automatisation des tests", "QA santé"]})

    assert any("automatisation+des+tests" in u for u in captured)
    assert any("QA+sant" in u for u in captured)
    assert not any("test+manager" in u for u in captured)  # défauts non utilisés
