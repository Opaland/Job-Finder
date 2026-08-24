"""Tests du mini-CRM contacts."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Profile


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    db.add(Profile(id=1, sources_enabled={}))
    db.commit()

    def override():
        yield db

    fastapi_app.dependency_overrides[get_db] = override
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()
    db.close()


def test_cycle_de_vie_contact(client):
    created = client.post("/api/contacts", json={
        "company": "ACME Santé", "name": "Claire Dupont",
        "role": "Talent Acquisition", "email": "c.dupont@acme.fr",
    })
    assert created.status_code == 201
    cid = created.json()["id"]

    # Filtre par entreprise (insensible à la casse).
    assert len(client.get("/api/contacts?company=acme santé").json()) == 1
    assert client.get("/api/contacts?company=Autre").json() == []

    updated = client.patch(f"/api/contacts/{cid}", json={"phone": "06 00 00 00 00"})
    assert updated.json()["phone"] == "06 00 00 00 00"
    assert updated.json()["name"] == "Claire Dupont"

    assert client.delete(f"/api/contacts/{cid}").json()["deleted"] is True
    assert client.get("/api/contacts").json() == []


def test_contact_sans_nom_refuse(client):
    resp = client.post("/api/contacts", json={"company": "ACME", "name": "  "})
    assert resp.status_code == 400
    assert "nom" in resp.json()["detail"].lower()
