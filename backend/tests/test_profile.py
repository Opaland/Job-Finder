"""PUT /api/profile : un champ obligatoire vidé ne doit ni planter ni effacer le reste."""
from app.models import Profile


def test_champ_obligatoire_a_null_est_rejete_proprement(client, db):
    """Avant correction : IntegrityError SQLite → 500 brut (NOT NULL constraint)."""
    resp = client.put("/api/profile", json={"radius_km": None})
    assert resp.status_code == 400
    assert "radius_km" in resp.json()["detail"]


def test_champ_obligatoire_a_null_ne_perd_pas_les_autres_champs_de_la_requete(client, db):
    """La transaction entière doit être refusée, pas appliquée en partie."""
    avant = db.get(Profile, 1).weekly_goal
    resp = client.put("/api/profile", json={"weekly_goal": 10, "radius_km": None})
    assert resp.status_code == 400
    db.refresh(db.get(Profile, 1))
    assert db.get(Profile, 1).weekly_goal == avant, "weekly_goal n'aurait pas dû être écrit"


def test_champ_optionnel_a_null_reste_accepte(client, db):
    """min_salary est réellement nullable en base : null doit continuer à marcher."""
    resp = client.put("/api/profile", json={"min_salary": None})
    assert resp.status_code == 200


def test_mise_a_jour_normale_fonctionne_toujours(client, db):
    resp = client.put("/api/profile", json={"radius_km": 60, "weekly_goal": 8})
    assert resp.status_code == 200
    assert resp.json()["radius_km"] == 60
    assert resp.json()["weekly_goal"] == 8
