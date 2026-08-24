"""Socle commun des connecteurs de sites d'emploi.

Chaque connecteur renvoie une liste de RawOffer normalisées. Un connecteur qui
échoue (clé absente, site indisponible, format changé) ne bloque jamais le scan :
l'erreur est enregistrée dans les statistiques du scan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


@dataclass
class RawOffer:
    source: str
    source_id: str
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    contract_type: str = ""
    salary_text: str = ""
    remote: bool = False
    published_at: datetime | None = None


@dataclass
class ConnectorResult:
    offers: list[RawOffer] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Connector:
    """Interface d'un connecteur. `name` est l'identifiant technique, `label` le nom affiché."""

    name = "base"
    label = "Base"
    needs_key = False

    def is_configured(self) -> bool:
        return True

    def fetch(self, profile: dict) -> ConnectorResult:  # pragma: no cover - interface
        raise NotImplementedError

    def client(self) -> httpx.Client:
        return httpx.Client(headers=DEFAULT_HEADERS, timeout=30, follow_redirects=True)


def dedupe_raw(offers: list[RawOffer]) -> list[RawOffer]:
    """Dédoublonne par (source, source_id) au sein d'un même connecteur."""
    seen: set[tuple[str, str]] = set()
    out = []
    for offer in offers:
        key = (offer.source, offer.source_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(offer)
    return out
