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


def _make_backup(path, with_tables=True, offers=2):
    con = sqlite3.connect(path)
    if with_tables:
        con.execute("CREATE TABLE offers (id INTEGER PRIMARY KEY, title TEXT)")
        con.execute("CREATE TABLE profile (id INTEGER PRIMARY KEY)")
        for i in range(offers):
            con.execute("INSERT INTO offers (title) VALUES (?)", (f"Offre {i}",))
    else:
        con.execute("CREATE TABLE autre (id INTEGER)")
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
