"""Garde-fou : chaque test travaille dans un dossier temporaire (QAK_RACINE). Aucun test
ne lit ni n'écrit la vraie bibliothèque ou la vraie base de connaissances du dépôt."""
import shutil
import sys
from pathlib import Path

import pytest

RACINE_CODE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE_CODE))
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def racine_isolee(tmp_path, monkeypatch):
    monkeypatch.setenv("QAK_RACINE", str(tmp_path))
    from qak import chemins
    assert chemins.racine() == tmp_path
    yield tmp_path


@pytest.fixture
def bibliotheque_test(racine_isolee):
    """Bibliothèque indexée avec le syllabus fictif v9.9."""
    from qak import bibliotheque
    r = bibliotheque.importer(FIXTURES / "syllabus_v9.pdf")
    assert r["etat"] == "importe", r
    return r["doc_id"]


@pytest.fixture
def copie_fixture(tmp_path):
    def copier(nom, vers=None):
        cible = tmp_path / (vers or nom)
        shutil.copy2(FIXTURES / nom, cible)
        return cible
    return copier
