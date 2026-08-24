"""Connecteur Welcome to the Jungle (best-effort, sans clé officielle).

WTTJ n'a pas d'API publique documentée : la recherche du site s'appuie sur
Algolia. L'app id public est stable (CSEKHVMS53) mais la clé de recherche
publique peut changer. Si le connecteur ne renvoie rien :
  1. Ouvrir https://www.welcometothejungle.com/fr/jobs dans le navigateur
  2. F12 → onglet Réseau → filtrer « algolia » → copier le paramètre
     x-algolia-api-key d'une requête
  3. Le coller dans .env : WTTJ_ALGOLIA_API_KEY=...
"""
from __future__ import annotations

from ..config import settings
from .base import Connector, ConnectorResult, RawOffer, dedupe_raw

# Clé de recherche publique observée sur le site (peut changer, cf. docstring).
DEFAULT_PUBLIC_KEY = "02f0dd12736ad34acd7018e12a3b1f47"

INDEX = "wttj_jobs_production_fr"


class WTTJConnector(Connector):
    name = "wttj"
    label = "Welcome to the Jungle"
    needs_key = False

    def _api_key(self) -> str:
        return settings.wttj_algolia_api_key or DEFAULT_PUBLIC_KEY

    def _parse(self, hit: dict) -> RawOffer:
        org = hit.get("organization") or {}
        offices = hit.get("offices") or []
        city = ""
        if offices and isinstance(offices, list):
            city = (offices[0] or {}).get("city", "") or ""
        if not city:
            city = hit.get("city", "") or ""
        slug = hit.get("slug", "")
        org_slug = org.get("slug", "")
        url = f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}" if slug and org_slug else ""
        remote = str(hit.get("remote", "")).lower() in ("fulltime", "full", "yes", "true")
        contract = hit.get("contract_type", "") or ""
        mapping = {"full_time": "CDI", "temporary": "CDD", "freelance": "Freelance", "internship": "Stage", "apprenticeship": "Alternance"}
        desc = hit.get("profile", "") or hit.get("description", "") or ""
        return RawOffer(
            source=self.name,
            source_id=str(hit.get("objectID", "") or hit.get("reference", "") or slug),
            title=hit.get("name", ""),
            company=org.get("name", ""),
            location=city,
            description=desc,
            url=url,
            contract_type=mapping.get(contract, contract),
            remote=remote,
        )

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        url = f"https://{settings.wttj_algolia_app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
        headers = {
            "X-Algolia-Application-Id": settings.wttj_algolia_app_id,
            "X-Algolia-API-Key": self._api_key(),
            "Content-Type": "application/json",
        }
        searches = [
            {"query": "test manager", "aroundLatLng": "45.7578,4.8320", "aroundRadius": profile.get("radius_km", 40) * 1000},
            {"query": "QA", "aroundLatLng": "45.7578,4.8320", "aroundRadius": profile.get("radius_km", 40) * 1000},
            {"query": "QA lead", "filters": "remote:fulltime"},
            {"query": "test manager", "filters": "remote:fulltime"},
        ]
        requests_payload = {
            "requests": [
                {
                    "indexName": INDEX,
                    "params": "&".join(
                        [f"query={s['query']}", "hitsPerPage=50"]
                        + [f"{k}={v}" for k, v in s.items() if k != "query"]
                    ),
                }
                for s in searches
            ]
        }
        with self.client() as client:
            try:
                resp = client.post(url, json=requests_payload, headers=headers)
                resp.raise_for_status()
                for res in resp.json().get("results", []):
                    for hit in res.get("hits", []):
                        offer = self._parse(hit)
                        if offer.title:
                            result.offers.append(offer)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(
                    f"Recherche WTTJ impossible ({exc}). La clé Algolia publique a peut-être changé : "
                    "voir le README, section Welcome to the Jungle."
                )

        result.offers = dedupe_raw(result.offers)
        return result
