"""GET /api/sources : signal informatif sur une source muette depuis longtemps (issue #3)."""
from datetime import timedelta

from app.models import ScanRun, local_now


def _run(db, il_y_a, fetched_wttj):
    db.add(ScanRun(
        status="termine",
        started_at=local_now() - timedelta(days=il_y_a),
        finished_at=local_now() - timedelta(days=il_y_a),
        source_stats={"wttj": {"label": "Welcome to the Jungle", "fetched": fetched_wttj,
                                "new": 0, "seen": 0, "errors": []}},
    ))
    db.commit()


def test_source_muette_depuis_longtemps_est_signalee(client, db):
    """WTTJ en panne depuis 40 jours (aucun `fetched > 0` dans la fenêtre observée)
    ne doit jamais avoir été balayée (still_online) — mais ça, c'est scan.py.
    Ici : /api/sources doit quand même dire depuis quand elle est muette."""
    _run(db, il_y_a=45, fetched_wttj=12)   # dernière fois où elle a réussi
    _run(db, il_y_a=5, fetched_wttj=0)     # scans récents : toujours à vide
    resp = client.get("/api/sources")
    wttj = next(s for s in resp.json()["sources"] if s["name"] == "wttj")
    assert wttj["dernier_resultat"]["il_y_a_jours"] == 45


def test_source_qui_vient_de_reussir_n_est_pas_signalee(client, db):
    _run(db, il_y_a=1, fetched_wttj=8)
    resp = client.get("/api/sources")
    wttj = next(s for s in resp.json()["sources"] if s["name"] == "wttj")
    assert wttj["dernier_resultat"]["il_y_a_jours"] == 1


def test_source_jamais_vue_dans_la_fenetre_observee_renvoie_none(client, db):
    _run(db, il_y_a=2, fetched_wttj=0)
    resp = client.get("/api/sources")
    wttj = next(s for s in resp.json()["sources"] if s["name"] == "wttj")
    assert wttj["dernier_resultat"] is None
