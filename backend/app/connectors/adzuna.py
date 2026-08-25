"""Connecteur Adzuna — agrégateur multi-sites (API officielle gratuite).

Clés sur https://developer.adzuna.com : ADZUNA_APP_ID et ADZUNA_APP_KEY dans .env.
Adzuna agrège de nombreux jobboards français, ce qui élargit la couverture
au-delà des sites interrogés directement.
"""
from __future__ import annotations

from ..config import settings
from .base import Connector, ConnectorResult, RawOffer, dedupe_raw, parse_published, profile_queries

BASE_URL = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"


class AdzunaConnector(Connector):
    name = "adzuna"
    label = "Adzuna (agrégateur)"
    needs_key = True

    def is_configured(self) -> bool:
        return bool(settings.adzuna_app_id and settings.adzuna_app_key)

    def _parse(self, item: dict) -> RawOffer:
        published = parse_published(item.get("created"))
        salary = ""
        if item.get("salary_min") or item.get("salary_max"):
            lo = int(item.get("salary_min") or 0)
            hi = int(item.get("salary_max") or 0)
            salary = f"{lo:,} € - {hi:,} € / an".replace(",", " ")
        contract = item.get("contract_type", "") or item.get("contract_time", "")
        mapping = {"permanent": "CDI", "contract": "CDD/Mission", "full_time": "Temps plein"}
        return RawOffer(
            source=self.name,
            source_id=str(item.get("id", "")),
            title=item.get("title", "").replace("<strong>", "").replace("</strong>", ""),
            company=(item.get("company") or {}).get("display_name", ""),
            location=(item.get("location") or {}).get("display_name", ""),
            description=item.get("description", ""),
            url=item.get("redirect_url", ""),
            contract_type=mapping.get(contract, contract),
            salary_text=salary,
            published_at=published,
        )

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        if not self.is_configured():
            result.errors.append("Clés ADZUNA_APP_ID / ADZUNA_APP_KEY absentes du .env")
            return result

        radius = int(profile.get("radius_km", 40))
        keywords = profile_queries(profile)
        queries = [{"what": kw, "where": "Lyon", "distance": radius} for kw in keywords[:4]]
        queries += [{"what": f"{kw} télétravail"} for kw in keywords[:2]]
        with self.client() as client:
            for query in queries:
                params = {
                    "app_id": settings.adzuna_app_id,
                    "app_key": settings.adzuna_app_key,
                    "results_per_page": 50,
                    "max_days_old": 45,
                    "content-type": "application/json",
                    **query,
                }
                try:
                    resp = client.get(BASE_URL.format(page=1), params=params)
                    resp.raise_for_status()
                    for item in resp.json().get("results", []):
                        result.offers.append(self._parse(item))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Requête {query.get('what')} : {exc}")

        result.offers = dedupe_raw(result.offers)
        return result
