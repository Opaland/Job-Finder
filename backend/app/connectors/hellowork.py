"""Connecteur HelloWork (best-effort, lecture des pages de recherche du site).

HelloWork n'a pas d'API publique : ce connecteur lit les pages de résultats
HTML. Le site peut changer sa structure ou limiter les robots ; dans ce cas les
erreurs apparaissent dans les statistiques du scan sans bloquer les autres
sources. La description complète est récupérée à l'ouverture de l'offre via son
lien d'origine.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import (
    Connector, ConnectorResult, RawOffer,
    aucune_offre, dedupe_raw, profile_queries, resume_erreur,
)

SEARCH_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html?k={kw}&l={loc}"
OFFER_RE = re.compile(r"/fr-fr/emplois/(\d+)\.html")

# Le site n'a pas de classes sémantiques (Tailwind) : les champs se
# reconnaissent à leur forme dans la carte. Structure relevée sur une vraie page
# le 27/08/2026 (figée dans tests/fixtures/hellowork_recherche.html) :
#   ['Suivi de candidature', 'Test Manager H/F', 'Stormshield',
#    'Lyon 9e - 69', 'CDI', 'Télétravail partiel', 'Voir l’offre',
#    'il y a 13 jours']
CONTRATS = {
    "cdi", "cdd", "intérim", "interim", "freelance", "alternance", "stage",
    "apprentissage", "indépendant", "independant", "cdi intérimaire",
}
# « Lyon 9e - 69 », « Villeurbanne - 69 », « 69100 »
LIEU_RE = re.compile(r"-\s*\d{2,3}\s*$|\b\d{5}\b")
PUBLIEE_RE = re.compile(r"il y a\s+(\d+)\s*(minute|heure|jour|semaine|mois)", re.IGNORECASE)
JOURS_PAR_UNITE = {"minute": 0, "heure": 0, "jour": 1, "semaine": 7, "mois": 30}
# Textes d'interface présents dans la carte, qui ne décrivent pas l'offre.
BRUIT = {
    "suivi de candidature", "voir l'offre", "voir l’offre", "nouveau",
    "urgent", "candidature facile", "offre sponsorisée",
}
# Au-delà, on est remonté dans la liste entière plutôt que dans une carte.
NIVEAUX_MAX = 6
# « Télétravail partiel » n'est PAS du télétravail complet : le scoring accorde
# 13 points sur 15 au full remote, les compter pour un jour par semaine
# gonflerait le score de toutes les offres lyonnaises.
PARTIEL = ("partiel", "ponctuel", "occasionnel", "hybride", "1 jour", "2 jours", "3 jours")


def _teletravail_complet(textes: list[str]) -> bool:
    for texte in textes:
        bas = texte.lower()
        if "télétravail" in bas or "remote" in bas:
            return not any(mot in bas for mot in PARTIEL)
    return False


class HelloWorkConnector(Connector):
    name = "hellowork"
    label = "HelloWork"
    needs_key = False

    @staticmethod
    def _carte(lien):
        """Remonte du lien jusqu'à la carte entière de l'offre.

        Critère structurel plutôt qu'un nombre de textes : la carte est le plus
        haut ancêtre qui ne contient encore QU'UNE seule offre. Au-delà, on
        embarquerait la carte voisine.

        Le parent immédiat, lui, ne porte que le titre et l'entreprise : s'y
        arrêter laissait le lieu vide sur TOUTES les offres, le contrat absent
        et une description de 35 caractères.
        """
        carte = lien
        noeud = lien
        for _ in range(NIVEAUX_MAX):
            parent = noeud.parent
            if parent is None or parent.name in ("body", "html"):
                break
            if len(parent.find_all("a", href=OFFER_RE)) > 1:
                break
            noeud = carte = parent
        return carte

    def _parse_page(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        for link in soup.find_all("a", href=OFFER_RE):
            href = link.get("href", "")
            match = OFFER_RE.search(href)
            if not match:
                continue

            carte = self._carte(link)
            textes = [
                t.strip() for t in carte.stripped_strings
                if t.strip() and t.strip().lower() not in BRUIT
            ]
            if not textes:
                continue

            title = textes[0]
            if len(title) < 4:
                continue

            location = next((t for t in textes if LIEU_RE.search(t)), "")
            contract = next((t for t in textes if t.lower() in CONTRATS), "")
            remote = _teletravail_complet(textes)
            published_at = self._publiee_le(textes)

            # L'entreprise est le premier texte restant une fois retirés le
            # titre et les champs déjà identifiés.
            deja_vus = {title, location, contract}
            company = next(
                (t for t in textes[1:]
                 if t not in deja_vus and not PUBLIEE_RE.search(t)
                 and "télétravail" not in t.lower() and len(t) < 80),
                "",
            )

            # La page de résultats ne porte pas de description : on résume les
            # faits de la carte plutôt que d'y coller du texte d'interface. La
            # description complète arrive par l'enrichissement de l'offre.
            description = " · ".join(x for x in (contract, location,
                                                 "Télétravail" if remote else "") if x)

            url = href if href.startswith("http") else f"https://www.hellowork.com{href}"
            offers.append(
                RawOffer(
                    source=self.name,
                    source_id=match.group(1),
                    title=title,
                    company=company,
                    location=location,
                    description=description,
                    url=url,
                    contract_type=contract,
                    remote=remote,
                    published_at=published_at,
                )
            )
        return offers

    @staticmethod
    def _publiee_le(textes: list[str]):
        """« il y a 13 jours » → date de publication approchée."""
        from datetime import timedelta

        from ..models import local_now

        for texte in textes:
            trouve = PUBLIEE_RE.search(texte)
            if trouve:
                nombre, unite = int(trouve.group(1)), trouve.group(2).lower()
                return local_now() - timedelta(days=nombre * JOURS_PAR_UNITE.get(unite, 0))
        return None

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        keywords = profile_queries(profile)
        searches = [(kw, "Lyon") for kw in keywords[:3]] + [(kw, "Télétravail") for kw in keywords[:2]]
        with self.client() as client:
            for kw, loc in searches:
                try:
                    resp = client.get(SEARCH_URL.format(kw=quote_plus(kw), loc=quote_plus(loc)))
                    resp.raise_for_status()
                    result.offers.extend(self._parse_page(resp.text))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Recherche « {kw} / {loc} » : {resume_erreur(exc)}")

        result.offers = dedupe_raw(result.offers)
        if not result.offers and not result.errors:
            result.errors.append(aucune_offre("la structure du site HelloWork a probablement changé."))
        return result
