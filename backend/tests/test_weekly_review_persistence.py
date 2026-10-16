"""Le bilan hebdomadaire IA est maintenant persisté (issue #31) : avant, il ne
survivait ni à un changement d'onglet ni à un rechargement de la page.
"""
from app.models import WeeklyReview
from app.services import claude_ai


def test_aucun_bilan_au_depart(client, db):
    assert client.get("/api/digests/weekly-review/last").json() is None


def test_le_bilan_genere_est_persiste_et_relisible(client, db, monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    monkeypatch.setattr(claude_ai, "ai_bilan_hebdo", lambda resume, cv: "Bonne semaine, continue ainsi.")

    genere = client.post("/api/digests/weekly-review")
    assert genere.status_code == 200
    assert genere.json()["bilan"] == "Bonne semaine, continue ainsi."
    assert db.query(WeeklyReview).count() == 1

    relu = client.get("/api/digests/weekly-review/last").json()
    assert relu["bilan"] == "Bonne semaine, continue ainsi."
    assert relu["created_at"]


def test_une_regeneration_garde_l_historique_et_renvoie_le_plus_recent(client, db, monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    monkeypatch.setattr(claude_ai, "ai_bilan_hebdo", lambda resume, cv: "Premier bilan.")
    client.post("/api/digests/weekly-review")

    monkeypatch.setattr(claude_ai, "ai_bilan_hebdo", lambda resume, cv: "Deuxième bilan, plus récent.")
    client.post("/api/digests/weekly-review")

    assert db.query(WeeklyReview).count() == 2
    assert client.get("/api/digests/weekly-review/last").json()["bilan"] == "Deuxième bilan, plus récent."
