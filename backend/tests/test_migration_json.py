"""Colonnes JSON ajoutées à une base existante : jamais NULL.

Régression trouvée en conditions réelles : après mise à jour, les colonnes JSON
nouvellement ajoutées valaient NULL sur les lignes existantes, et l'API
renvoyait une erreur 500 au premier affichage de la liste d'offres.
"""
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import ensure_schema, get_db
from app.main import app as fastapi_app


def test_colonnes_json_remplies_apres_migration(tmp_path):
    chemin = tmp_path / "ancienne.db"

    # Base « d'avant » : offers et profile sans les colonnes JSON récentes.
    brute = sqlite3.connect(chemin)
    brute.executescript("""
        CREATE TABLE offers (
            id INTEGER PRIMARY KEY, fingerprint TEXT, source TEXT, source_id TEXT,
            title TEXT, company TEXT, location TEXT, description TEXT, url TEXT,
            contract_type TEXT, salary_text TEXT, remote BOOLEAN,
            published_at DATETIME, collected_at DATETIME, last_seen_at DATETIME,
            still_online BOOLEAN, score FLOAT, score_breakdown JSON, ai_score FLOAT,
            ai_reason TEXT, final_score FLOAT, status TEXT, status_history JSON,
            favorite BOOLEAN, notes TEXT, cover_letter TEXT, other_sources JSON
        );
        CREATE TABLE profile (id INTEGER PRIMARY KEY, full_name TEXT, cv_text TEXT);
        INSERT INTO offers (id, fingerprint, source, source_id, title, company, location,
                            description, url, contract_type, salary_text, ai_reason, notes,
                            cover_letter, favorite, status, score, final_score, remote, still_online,
                            collected_at, last_seen_at)
        VALUES (1, 'fp', 'apec', 'a1', 'Test Manager', 'ACME', 'Lyon',
                'Description', 'https://exemple.fr', 'CDI', '', '', '',
                '', 0, 'nouvelle', 80, 80, 0, 1, '2026-08-01 09:00:00', '2026-08-01 09:00:00');
        INSERT INTO profile (id, full_name, cv_text) VALUES (1, 'Cédric Moretti', 'cv');
    """)
    brute.commit()
    brute.close()

    engine = create_engine(f"sqlite:///{chemin}")
    ensure_schema(engine)

    # Aucune colonne JSON ne doit rester NULL après migration.
    with engine.begin() as conn:
        for colonne in ("interviews", "checklist", "letter_versions", "other_sources"):
            valeur = conn.execute(text(f"SELECT {colonne} FROM offers WHERE id = 1")).scalar()
            assert valeur is not None, f"offers.{colonne} est NULL après migration"
        assert conn.execute(text("SELECT saved_searches FROM profile WHERE id = 1")).scalar() is not None

    # Et l'API sert la liste sans erreur (le symptôme d'origine).
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    def override():
        yield db

    fastapi_app.dependency_overrides[get_db] = override
    try:
        client = TestClient(fastapi_app)
        liste = client.get("/api/offers")
        assert liste.status_code == 200, liste.text
        item = liste.json()["items"][0]
        assert item["checklist"] == {}
        detail = client.get("/api/offers/1")
        assert detail.status_code == 200
        assert detail.json()["interviews"] == []
        assert detail.json()["letter_versions"] == []
        assert client.get("/api/profile").json()["saved_searches"] == []
    finally:
        fastapi_app.dependency_overrides.clear()
        db.close()
