"""Sprint 32 : recherches sauvegardées dans le profil."""
from app.routers.profile import MAX_RECHERCHES


def test_enregistrer_et_relire(client):
    resp = client.put("/api/profile", json={"saved_searches": [
        {"nom": "Pépites Lyon", "filtres": {"min_score": "85", "company": "Lyon"}},
    ]})
    assert resp.status_code == 200
    recherches = resp.json()["saved_searches"]
    assert recherches == [{"nom": "Pépites Lyon", "filtres": {"min_score": "85", "company": "Lyon"}}]
    # Persisté : relu tel quel.
    assert client.get("/api/profile").json()["saved_searches"] == recherches


def test_filtres_inconnus_et_vides_ecartes(client):
    resp = client.put("/api/profile", json={"saved_searches": [
        {"nom": "Test", "filtres": {"min_score": "70", "company": "", "inconnu": "x"}},
    ]})
    assert resp.json()["saved_searches"][0]["filtres"] == {"min_score": "70"}


def test_noms_vides_et_doublons_ecartes(client):
    resp = client.put("/api/profile", json={"saved_searches": [
        {"nom": "  ", "filtres": {}},
        {"nom": "Remote", "filtres": {"sort": "date"}},
        {"nom": "remote", "filtres": {"sort": "score"}},   # doublon (casse ignorée)
        "pas un objet",
    ]})
    noms = [r["nom"] for r in resp.json()["saved_searches"]]
    assert noms == ["Remote"]


def test_nombre_de_recherches_plafonne(client):
    trop = [{"nom": f"R{i}", "filtres": {"sort": "score"}} for i in range(MAX_RECHERCHES + 10)]
    resp = client.put("/api/profile", json={"saved_searches": trop})
    assert len(resp.json()["saved_searches"]) == MAX_RECHERCHES


def test_profil_sans_recherche(client):
    assert client.get("/api/profile").json()["saved_searches"] == []
