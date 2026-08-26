"""Fixtures partagées : base temporaire isolée + client API.

Les fichiers de tests plus anciens définissent encore leur propre fixture
`client` ; elle a la priorité sur celle-ci, aucun conflit.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Profile


@pytest.fixture(autouse=True)
def base_reelle_hors_de_portee(tmp_path, monkeypatch):
    """Aucun test ne doit pouvoir toucher `data/jobfinder.db`.

    Sans ce garde-fou, un test qui retombe par erreur sur la vraie base passe au
    vert sur un poste où elle existe et casse en CI, où `data/` est vide — c'est
    exactement ce qui est arrivé à la restauration (elle ouvrait une session sur
    `SessionLocal` au lieu du moteur qu'elle venait de migrer).

    Rediriger `settings.db_path` ne suffit pas : `engine` et `SessionLocal` sont
    construits à l'import, avec le chemin d'alors. Et les patcher dans
    `app.database` ne suffit pas non plus — `main.py`, `cli.py` et les routeurs
    font `from ..database import engine`, ce qui fige la référence à leur propre
    chargement. On remplace donc aussi les noms déjà liés, partout où ils
    pointent encore vers les vrais objets. La base de remplacement est vide :
    un accès accidentel échoue bruyamment au lieu de réussir silencieusement.
    """
    import sys

    import app.database as database

    chemin = tmp_path / "hors-de-portee.db"
    monkeypatch.setattr(settings, "db_path", str(chemin))
    moteur = create_engine(f"sqlite:///{chemin}")
    fabrique = sessionmaker(bind=moteur, autoflush=False, expire_on_commit=False)

    remplacements = {"engine": (database.engine, moteur),
                     "SessionLocal": (database.SessionLocal, fabrique)}
    modules = [m for nom, m in list(sys.modules.items())
               if nom == "app.database" or nom.startswith("app.")]
    for module in modules:
        for attribut, (reel, remplacant) in remplacements.items():
            if getattr(module, attribut, None) is reel:
                monkeypatch.setattr(module, attribut, remplacant)


@pytest.fixture()
def db(tmp_path):
    """Session sur une base SQLite neuve, avec le profil obligatoire (id=1)."""
    engine = create_engine(f"sqlite:///{tmp_path}/jobfinder-test.db")
    Base.metadata.create_all(engine)
    # Mêmes réglages que SessionLocal (database.py) : sans cela, autoflush
    # masquerait des bugs que la production a bel et bien.
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
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
