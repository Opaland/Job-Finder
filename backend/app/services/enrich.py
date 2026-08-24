"""Récupération de la description complète d'une offre depuis sa page d'origine.

Certaines sources (HelloWork, listes de résultats) ne fournissent qu'un extrait :
ce service ouvre la page de l'offre et en extrait le bloc de texte principal.
Heuristique volontairement générique — en cas d'échec, l'offre garde son extrait.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from ..connectors.base import DEFAULT_HEADERS

# Balises dont le contenu n'est jamais du texte d'offre. « header » n'y figure
# pas : dans une annonce HTML5, <header> contient souvent le titre du poste —
# seul le bandeau de site (header direct du body) est retiré plus bas.
NOISE_TAGS = ["script", "style", "nav", "footer", "aside", "form", "noscript", "svg", "iframe", "button"]


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_main_text(html: str) -> str:
    """Extrait le bloc de texte principal d'une page (le plus long, au plus profond)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    body = soup.body or soup
    for banner in body.find_all("header", recursive=False):
        banner.decompose()
    total = len(body.get_text(" ", strip=True))
    if total == 0:
        return ""

    best = body
    # Descend vers l'élément le plus profond qui conserve l'essentiel du texte :
    # on élimine ainsi menus et colonnes annexes sans dépendre du site.
    progressed = True
    while progressed:
        progressed = False
        best_len = len(best.get_text(" ", strip=True))
        for child in best.find_all(["main", "article", "section", "div"], recursive=False):
            child_len = len(child.get_text(" ", strip=True))
            if child_len >= 0.7 * best_len and child_len > 0:
                best = child
                progressed = True
                break
    return _clean_text(best.get_text("\n", strip=True))


def fetch_full_description(url: str) -> str | None:
    """Renvoie le texte principal de la page de l'offre, ou None si indisponible."""
    if not url or not url.startswith("http"):
        return None
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if "text/html" not in resp.headers.get("content-type", "text/html"):
                return None
            text = extract_main_text(resp.text)
    except Exception:  # noqa: BLE001 — best-effort, l'extrait existant reste en place
        return None
    return text if len(text) >= 300 else None
