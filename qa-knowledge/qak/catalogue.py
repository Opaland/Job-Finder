"""Catalogue des syllabus ISTQB officiels : vérification de disponibilité et téléchargement.

Seuls les domaines listés dans `domaines_autorises` du catalogue sont acceptés, y compris
après redirection : aucun document n'est récupéré depuis une source non officielle.
"""
import re
from datetime import date
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import bibliotheque, chemins

AGENT = "qa-knowledge/1.0 (bibliotheque locale ISTQB)"


def documents(codes: list[str] | None = None, niveau: str | None = None) -> list[dict]:
    cat = bibliotheque.catalogue()["documents"]
    if codes:
        voulus = {c.lower() for c in codes}
        inconnus = voulus - {d["code"].lower() for d in cat}
        if inconnus:
            raise KeyError(f"Codes absents du catalogue : {', '.join(sorted(inconnus))}. Voir `catalogue`.")
        cat = [d for d in cat if d["code"].lower() in voulus]
    if niveau:
        cat = [d for d in cat if d["niveau"] == niveau]
    return cat


def _autorise(url: str) -> bool:
    hote = urlparse(url).hostname or ""
    return any(hote == d or hote.endswith("." + d) for d in bibliotheque.catalogue()["domaines_autorises"])


def _ouvrir(url: str, methode: str = "GET", delai: int = 60):
    if not _autorise(url):
        raise PermissionError(f"domaine non officiel refusé : {urlparse(url).hostname}")
    req = urllib.request.Request(url, method=methode, headers={"User-Agent": AGENT})
    rep = urllib.request.urlopen(req, timeout=delai)
    if not _autorise(rep.geturl()):
        rep.close()
        raise PermissionError(f"redirection vers un domaine non officiel refusée : {urlparse(rep.geturl()).hostname}")
    return rep


def _nom_fichier(rep) -> str:
    cd = rep.headers.get("Content-Disposition", "")
    m = re.search(r'filename="?([^";]+)"?', cd)
    nom = m.group(1) if m else Path(urlparse(rep.geturl()).path).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nom) or "document.pdf"


def verifier(doc: dict) -> dict:
    """Disponibilité et nom du fichier servi. Un nom différent de `fichier_constate`
    signale probablement une nouvelle version publiée par l'ISTQB."""
    try:
        with _ouvrir(doc["telechargement"], "HEAD", delai=30) as rep:
            nom = _nom_fichier(rep)
            type_ = rep.headers.get("Content-Type", "")
        etat = "disponible" if "pdf" in type_ or nom.lower().endswith(".pdf") else f"réponse inattendue ({type_})"
        change = nom != doc["fichier_constate"]
        return {"code": doc["code"], "etat": etat, "fichier": nom, "nouveau_fichier": change}
    except (urllib.error.URLError, OSError, PermissionError) as exc:
        return {"code": doc["code"], "etat": f"injoignable ({type(exc).__name__} : {str(exc)[:80]})",
                "fichier": None, "nouveau_fichier": False}


def telecharger(doc: dict) -> dict:
    """Télécharge le syllabus officiel dans bibliotheque/sources/ puis l'importe."""
    try:
        with _ouvrir(doc["telechargement"], delai=120) as rep:
            nom, url_finale, contenu = _nom_fichier(rep), rep.geturl(), rep.read()
    except (urllib.error.URLError, OSError, PermissionError) as exc:
        return {"etat": "echec", "fichier": doc["code"], "message": f"téléchargement impossible : {exc}"}
    if not contenu.startswith(b"%PDF"):
        return {"etat": "echec", "fichier": nom, "message": "le fichier reçu n'est pas un PDF (page d'erreur ?)"}
    dossier = chemins.sources()
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / nom
    if cible.exists() and cible.read_bytes() != contenu:
        # Même nom, contenu différent : nouvelle version. L'ancienne reste consultable.
        cible = dossier / f"{cible.stem}-{date.today().isoformat()}{cible.suffix}"
    cible.write_bytes(contenu)
    meta = {"code": doc["code"], "niveau": doc["niveau"], "domaine": doc["domaine"],
            "page_officielle": doc["page_officielle"],
            "source_officielle": url_finale if url_finale != doc["telechargement"] else doc["telechargement"],
            "origine": "téléchargement officiel istqb.org"}
    rapport = bibliotheque.importer(cible, meta_forcee=meta, copier=False)
    if rapport["etat"] == "doublon":
        cible.unlink(missing_ok=True)  # déjà présent sous un autre nom : on ne garde pas deux copies
    return rapport
