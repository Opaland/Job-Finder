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

from .base import Connector, ConnectorResult, RawOffer, dedupe_raw

SEARCH_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html?k={kw}&l={loc}"
OFFER_RE = re.compile(r"/fr-fr/emplois/(\d+)\.html")


class HelloWorkConnector(Connector):
    name = "hellowork"
    label = "HelloWork"
    needs_key = False

    def _parse_page(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        for link in soup.find_all("a", href=OFFER_RE):
            href = link.get("href", "")
            match = OFFER_RE.search(href)
            if not match:
                continue
            offer_id = match.group(1)
            container = link.find_parent(["li", "article", "div"]) or link
            texts = [t.strip() for t in container.stripped_strings if t.strip()]
            title = link.get_text(" ", strip=True) or (texts[0] if texts else "")
            if not title or len(title) < 4:
                continue
            company = ""
            location = ""
            contract = ""
            for text in texts[1:8]:
                low = text.lower()
                if not contract and low in ("cdi", "cdd", "intérim", "interim", "freelance", "alternance", "stage", "indépendant"):
                    contract = text
                elif not location and re.search(r"\b\d{2}\b|lyon|paris|télétravail|remote", low):
                    location = text
                elif not company and text != title and len(text) < 60:
                    company = text
            url = href if href.startswith("http") else f"https://www.hellowork.com{href}"
            offers.append(
                RawOffer(
                    source=self.name,
                    source_id=offer_id,
                    title=title,
                    company=company,
                    location=location,
                    description=" · ".join(texts[:12]),
                    url=url,
                    contract_type=contract,
                    remote="télétravail" in " ".join(texts).lower(),
                )
            )
        return offers

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        searches = [
            ("test manager", "Lyon"),
            ("QA", "Lyon"),
            ("responsable test", "Lyon"),
            ("test manager", "Télétravail"),
            ("QA lead", "Télétravail"),
        ]
        with self.client() as client:
            for kw, loc in searches:
                try:
                    resp = client.get(SEARCH_URL.format(kw=quote_plus(kw), loc=quote_plus(loc)))
                    resp.raise_for_status()
                    result.offers.extend(self._parse_page(resp.text))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Recherche « {kw} / {loc} » : {exc}")

        result.offers = dedupe_raw(result.offers)
        if not result.offers and not result.errors:
            result.errors.append("Aucune offre extraite (structure du site probablement modifiée).")
        return result
