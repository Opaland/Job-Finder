"""Tests de la restauration de sauvegarde."""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import app.routers.stats as stats_module
from app.config import settings
from app.database import Base
from app.main import app as fastapi_app


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Base courante + moteur isolés dans tmp_path (ne touche pas à data/)."""
    current = tmp_path / "courante.db"
    test_engine = create_engine(f"sqlite:///{current}")
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(settings, "db_path", str(current))
    monkeypatch.setattr(stats_module, "engine", test_engine)
    return {"path": current, "engine": test_engine, "client": TestClient(fastapi_app)}


def _make_backup(path, with_tables=True, offers=2, colonnes_completes=True):
    """Sauvegarde plausible : les colonnes indispensables sont présentes."""
    con = sqlite3.connect(path)
    if not with_tables:
        con.execute("CREATE TABLE autre (id INTEGER)")
    elif colonnes_completes:
        con.execute(
            "CREATE TABLE offers (id INTEGER PRIMARY KEY, fingerprint TEXT, source TEXT, "
            "source_id TEXT, title TEXT, collected_at DATETIME)"
        )
        con.execute("CREATE TABLE profile (id INTEGER PRIMARY KEY)")
        for i in range(offers):
            con.execute(
                "INSERT INTO offers (fingerprint, source, source_id, title, collected_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"fp{i}", "france_travail", str(i), f"Offre {i}", "2026-08-01 09:00:00"),
            )
    else:
        # Une base étrangère qui a par hasard les bons noms de tables.
        con.execute("CREATE TABLE offers (id INTEGER PRIMARY KEY, title TEXT)")
        con.execute("CREATE TABLE profile (id INTEGER PRIMARY KEY, pseudo TEXT)")
        con.execute("INSERT INTO offers (title) VALUES ('sans rapport')")
    con.commit()
    con.close()


def test_restauration_valide(env, tmp_path):
    backup = tmp_path / "sauvegarde.db"
    _make_backup(backup, offers=3)

    resp = env["client"].post("/api/restore", files={"file": ("sauvegarde.db", backup.read_bytes())})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["restored"] is True and data["offers"] == 3
    # Copie de sécurité créée à côté de la base.
    assert any(f.name.startswith("avant_restauration_") for f in env["path"].parent.iterdir())
    # La base restaurée a été migrée : les colonnes récentes existent.
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM offers")).fetchone()[0] == 3
        conn.execute(text("SELECT interview_prep FROM offers LIMIT 1"))


def test_fichier_non_sqlite_refuse(env):
    resp = env["client"].post("/api/restore", files={"file": ("pas_une_base.db", b"bonjour")})
    assert resp.status_code == 400
    assert "SQLite" in resp.json()["detail"]


def test_base_etrangere_refusee(env, tmp_path):
    other = tmp_path / "etrangere.db"
    _make_backup(other, with_tables=False)
    resp = env["client"].post("/api/restore", files={"file": ("etrangere.db", other.read_bytes())})
    assert resp.status_code == 400
    assert "Job Finder" in resp.json()["detail"]


def test_base_aux_bons_noms_de_tables_mais_au_mauvais_format_refusee(env, tmp_path):
    """Régression : une base étrangère ayant une table « offers » était acceptée,
    migrée, et laissait ensuite TOUTES les pages en 500 sans issue depuis l'UI."""
    etrangere = tmp_path / "etrangere.db"
    _make_backup(etrangere, colonnes_completes=False)

    avant = env["path"].read_bytes()
    reponse = env["client"].post("/api/restore",
                                 files={"file": ("etrangere.db", etrangere.read_bytes())})
    assert reponse.status_code == 400
    detail = reponse.json()["detail"]
    assert "colonnes manquantes" in detail and "collected_at" in detail
    assert env["path"].read_bytes() == avant, "la base courante doit rester intacte"


def test_les_copies_de_securite_ne_s_accumulent_pas(env, tmp_path):
    """Chaque copie contient CV, lettres et notes : on n'en garde que quelques-unes."""
    from app.routers.stats import COPIES_DE_SECURITE_GARDEES

    sauvegarde = tmp_path / "sauvegarde.db"
    _make_backup(sauvegarde, offers=1)
    for numero in range(COPIES_DE_SECURITE_GARDEES + 3):
        reponse = env["client"].post("/api/restore",
                                     files={"file": (f"s{numero}.db", sauvegarde.read_bytes())})
        assert reponse.status_code == 200, reponse.text

    copies = list(env["path"].parent.glob("avant_restauration_*.db"))
    assert len(copies) <= COPIES_DE_SECURITE_GARDEES, [c.name for c in copies]
