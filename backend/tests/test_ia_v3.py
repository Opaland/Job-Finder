"""Sprints 36-38 : nouvelles fonctions IA (contrat et repli sans CLI)."""
from app.models import Offer, local_now
from app.services import claude_ai


def _offre(db):
    offer = Offer(fingerprint="fp-ia", source="manuelle", source_id="ia1",
                  title="Test Manager", company="ACME", description="Pilotage QA, Selenium.",
                  final_score=90.0)
    db.add(offer)
    db.commit()
    return offer


def test_sans_cli_les_routes_ia_repondent_503(client, db, monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: False)
    offer = _offre(db)
    for chemin in (f"/api/offers/{offer.id}/simulation", f"/api/offers/{offer.id}/ats"):
        resp = client.post(chemin, json={"echange": []})
        assert resp.status_code == 503
        assert "claude" in resp.json()["detail"].lower()
    resp = client.post("/api/digests/weekly-review")
    assert resp.status_code == 503


def test_simulation_renvoie_question_retour_conseil(client, db, monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    monkeypatch.setattr(claude_ai, "_run_claude", lambda *a, **k: (
        '{"retour": "Réponse trop générale.", "question": "Comment pilotez-vous une campagne ?",'
        ' "conseil": "Il cherche votre méthode."}'
    ))
    offer = _offre(db)
    resp = client.post(f"/api/offers/{offer.id}/simulation",
                       json={"echange": [{"question": "Présentez-vous", "reponse": "15 ans de QA."}]})
    assert resp.status_code == 200
    tour = resp.json()
    assert tour["question"].startswith("Comment")
    assert tour["retour"] and tour["conseil"]


def test_simulation_reponse_illisible(client, db, monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    monkeypatch.setattr(claude_ai, "_run_claude", lambda *a, **k: "pas du JSON")
    offer = _offre(db)
    resp = client.post(f"/api/offers/{offer.id}/simulation", json={"echange": []})
    assert resp.status_code == 502


def test_reformulation_ats_stockee(client, db, monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    monkeypatch.setattr(claude_ai, "_run_claude", lambda *a, **k: "TITRE DU CV : Test Manager QA")
    offer = _offre(db)
    resp = client.post(f"/api/offers/{offer.id}/ats")
    assert resp.status_code == 200
    assert "TITRE DU CV" in resp.json()["ats_reformulation"]
    # Persistée sur l'offre.
    assert "TITRE DU CV" in client.get(f"/api/offers/{offer.id}").json()["ats_reformulation"]


def test_lettre_transmet_la_reserve_et_limite_a_deux_experiences(monkeypatch):
    """Issue #42 : testé en réel, la lettre générée dépassait la consigne de
    mots, listait jusqu'à 6 employeurs façon CV en prose, et ignorait une
    réserve que l'affinage IA du score avait pourtant déjà détectée (alors
    que la fiche de préparation d'entretien, elle, la reçoit et l'aborde
    bien). Vérifié ici que le prompt transmet bien cette réserve et borne
    explicitement le nombre d'expériences."""
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    prompts = []
    monkeypatch.setattr(claude_ai, "_run_claude", lambda prompt, **k: prompts.append(prompt) or "Lettre.")

    claude_ai.ai_cover_letter(
        {"title": "Test Manager", "company": "ACME", "location": "Lyon", "description": "..."},
        "CV complet.", "Lettre type.",
        ai_reason="contexte ESN/conseil qu'il n'a connu qu'à l'époque Solutec",
    )
    assert "Solutec" in prompts[0]
    assert "DEUX" in prompts[0]


def test_lettre_sans_reserve_connue_ne_mentionne_aucune_reserve(monkeypatch):
    monkeypatch.setattr(claude_ai, "cli_available", lambda: True)
    prompts = []
    monkeypatch.setattr(claude_ai, "_run_claude", lambda prompt, **k: prompts.append(prompt) or "Lettre.")

    claude_ai.ai_cover_letter(
        {"title": "Test Manager", "company": "ACME", "location": "Lyon", "description": "..."},
        "CV complet.", "Lettre type.",
    )
    assert "Réserve déjà identifiée" not in prompts[0]


def test_resume_semaine_compte_les_actes(client, db):
    """Le bilan s'appuie sur des chiffres réels, IA ou pas."""
    from app.services.digest import resume_semaine
    offer = _offre(db)
    offer.status_history = [
        {"status": "postulee", "date": local_now().isoformat(), "par": "utilisateur"},
        {"status": "entretien", "date": local_now().isoformat(), "par": "utilisateur"},
    ]
    db.commit()
    resume = resume_semaine(db)
    assert resume["candidatures_envoyees"] == 1
    assert resume["entretiens_obtenus"] == 1
    assert resume["nouvelles_offres_collectees"] == 1
    assert "objectif_hebdo" in resume


def test_chiffres_de_la_semaine_sans_ia(client, db):
    resp = client.get("/api/digests/weekly-summary")
    assert resp.status_code == 200
    assert resp.json()["candidatures_envoyees"] == 0
