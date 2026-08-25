"""Garde-fou : toute route de l'API doit être gérée en mode démo (GitHub Pages).

Règle du projet : une route oubliée casse la démo en ligne (« Endpoint non
simulé »). Une route est correctement gérée si :
  1. `frontend/src/demoApi.js` la traite — égalité, expression régulière ou
     règle de préfixe `route.startsWith('/api/...')` ;
  2. ou bien c'est un téléchargement / téléversement : il ne passe pas par la
     couche API simulée, le composant le bloque en amont avec un test `DEMO`.
     Ces routes sont listées ci-dessous ET vérifiées : le fichier frontend qui
     construit l'URL doit bien contenir une garde `DEMO`.

La correspondance porte sur le CHEMIN COMPLET (pas segment par segment) : une
route dont les mots existent ailleurs dans le fichier ne passe pas pour autant.
"""
import re
from pathlib import Path

from app.main import app

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
DEMO_API = FRONTEND / "demoApi.js"

# Routes de fichiers (téléchargement/téléversement) : gardées dans l'interface.
ROUTES_FICHIERS = {
    "/api/offers/export.xlsx",
    "/api/offers/{offer_id}/letter.docx",
    "/api/restore",
    "/api/profile/cv",
    "/api/exports/justificatif.pdf",
    "/api/exports/offres.csv",
}


def _motif_route(chemin: str) -> str:
    """Regex du chemin complet, paramètres acceptant leurs écritures JS.

    « /api/offers/{offer_id}/letter » accepte « /api/offers/(\\d+)/letter »
    (expression régulière de demoApi.js) comme « /api/offers/${id}/letter »
    (gabarit d'un composant).
    """
    parties = [
        r"[^/'\"`]+" if seg.startswith("{") else re.escape(seg)
        for seg in chemin.strip("/").split("/")
    ]
    return "/" + "/".join(parties)


def _sans_echappement(source: str) -> str:
    """Retire les « \\/ » des littéraux d'expression régulière JS pour comparer des chemins."""
    return source.replace("\\/", "/")


def _prefixes_demo(demo: str) -> list[str]:
    """Préfixes couverts en bloc, ex. route.startsWith('/api/digests/')."""
    return re.findall(r"startsWith\(['\"](/api[^'\"]*)['\"]\)", demo)


def _gardee_par_demo(chemin: str) -> bool:
    """L'URL complète est-elle construite dans un fichier frontend qui teste DEMO ?"""
    motif = _motif_route(chemin)
    for fichier in FRONTEND.rglob("*.js*"):
        contenu = _sans_echappement(fichier.read_text(encoding="utf-8"))
        if re.search(motif, contenu) and "DEMO" in contenu:
            return True
    return False


def test_toutes_les_routes_api_sont_gerees_en_demo():
    demo = _sans_echappement(DEMO_API.read_text(encoding="utf-8"))
    prefixes = _prefixes_demo(demo)
    # L'OpenAPI liste tous les chemins, y compris ceux des routeurs inclus
    # (app.routes les imbrique selon la version de FastAPI).
    manquantes = []
    for chemin in app.openapi().get("paths", {}):
        if not chemin.startswith("/api"):
            continue
        if chemin in ROUTES_FICHIERS:
            assert _gardee_par_demo(chemin), (
                f"{chemin} est déclarée comme route de fichier mais aucun composant "
                "frontend ne construit son URL avec une garde DEMO."
            )
            continue
        if any(chemin.startswith(p) for p in prefixes):
            continue
        if not re.search(_motif_route(chemin), demo):
            manquantes.append(chemin)

    assert not manquantes, (
        "Ces routes ne sont pas gérées dans frontend/src/demoApi.js : "
        + ", ".join(sorted(set(manquantes)))
        + " — simule-les, fais-les lever LOCAL_ONLY, ou ajoute-les à "
          "ROUTES_FICHIERS si ce sont des téléchargements gardés dans l'interface."
    )
