"""Fixtures partagées : base temporaire isolée + client API.

Les fichiers de tests plus anciens définissent encore leur propre fixture
`client` ; elle a la priorité sur celle-ci, aucun conflit.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Profile


@pytest.fixture()
def db(tmp_path):
    """Session sur une base SQLite neuve, avec le profil obligatoire (id=1)."""
    engine = create_engine(f"sqlite:///{tmp_path}/jobfinder-test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    session.add(Profile(id=1, sources_enabled={}))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    """Client HTTP branché sur la base de la fixture `db`."""
    def override():
        yield db

    fastapi_app.dependency_overrides[get_db] = override
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()
