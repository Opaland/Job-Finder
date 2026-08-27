"""Accès aux fichiers : ce que l'application accepte de lire et d'écrire.

L'application n'a volontairement ni authentification ni durcissement — c'est un
choix assumé pour un usage local. Mais les déploiements systemd et Docker
écoutent sur 0.0.0.0 : servir un fichier hors du build, ou écrire hors du
dossier d'uploads, n'est pas « pas de durcissement », c'est un défaut.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import DATA_DIR, FRONTEND_DIST
from app.main import app as fastapi_app

CHEMINS_PIEGES = [
    "../../data/jobfinder.db",
    "../../.env",
    "../../backend/app/config.py",
    "../../../etc/passwd",
    "./../../data/jobfinder.db",
    "..%2f..%2f.env",
]


@pytest.mark.skipif(not FRONTEND_DIST.exists(), reason="interface non buildée")
@pytest.mark.parametrize("chemin", CHEMINS_PIEGES)
def test_aucun_fichier_hors_du_build_n_est_servi(chemin):
    """Régression : « /../../data/jobfinder.db » renvoyait la base entière."""
    index = (FRONTEND_DIST / "index.html").read_bytes()
    with TestClient(fastapi_app) as client:
        reponse = client.get(f"/{chemin}")
    assert reponse.status_code == 200
    # Toute adresse inconnue rend l'application, jamais le fichier visé.
    assert reponse.content == index, f"« {chemin} » a servi autre chose que l'appli"


@pytest.mark.skipif(not FRONTEND_DIST.exists(), reason="interface non buildée")
def test_les_fichiers_du_build_restent_servis():
    """Le confinement ne doit pas casser le service normal."""
    with TestClient(fastapi_app) as client:
        assert client.get("/index.html").status_code == 200
        assert client.get("/offres").status_code == 200        # route interne React


CV_PLAUSIBLE = (
    "Cedric Moretti — Test Manager. Strategie de test, management d'equipe QA, "
    "automatisation Selenium et Cypress, tests API Postman, CI/CD GitLab, Jira, "
    "recette et homologation, ISTQB, agile scrum, pilotage des releases."
)


@pytest.mark.parametrize("nom_piege", ["../jobfinder.db", "..\\jobfinder.db", "dossier/cv.txt"])
def test_un_cv_ne_peut_pas_ecrire_hors_du_dossier_uploads(client, db, tmp_path, monkeypatch, nom_piege):
    """Régression : un fichier nommé « ../jobfinder.db » écrasait la base."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr("app.routers.profile.DATA_DIR", tmp_path)
    # La base de la fixture vit aussi dans tmp_path : on compare avant/après.
    avant = {f for f in tmp_path.rglob("*") if f.is_file()}

    reponse = client.post("/api/profile/cv",
                          files={"file": (nom_piege, CV_PLAUSIBLE.encode("utf-8"), "text/plain")})
    assert reponse.status_code == 200, reponse.text

    nouveaux = {f for f in tmp_path.rglob("*") if f.is_file()} - avant
    assert nouveaux, "le CV aurait dû être enregistré quelque part"
    hors_uploads = [f for f in nouveaux if f.parent != uploads]
    assert not hors_uploads, f"fichier écrit hors de uploads/ : {hors_uploads}"
    # Le nom retenu est un simple nom de fichier, sans aucun composant de chemin.
    nom_retenu = reponse.json()["cv_filename"]
    assert Path(nom_retenu).name == nom_retenu and "\\" not in nom_retenu


def test_le_cv_ne_passe_pas_par_la_ligne_de_commande(monkeypatch):
    """Le CV contient adresse, téléphone et email : argv est lisible par tout
    processus du poste (/proc/<pid>/cmdline, antivirus, dumps de plantage)."""
    from app.services import claude_ai

    vus = {}

    class FauxProcess:
        returncode = 0
        stdout = '{"result": "ok"}'

    def faux_run(commande, **kwargs):
        vus["commande"] = commande
        vus["stdin"] = kwargs.get("input")
        return FauxProcess()

    monkeypatch.setattr(claude_ai.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_ai.subprocess, "run", faux_run)

    secret = "8 rue des sources, 69530 Brignais · 06 85 90 77 67"
    claude_ai._run_claude(f"Analyse ce CV : {secret}")

    assert not any(secret in str(a) for a in vus["commande"]), "le CV est passé en argument"
    assert secret in vus["stdin"], "le prompt doit partir sur stdin"
