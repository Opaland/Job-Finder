"""Connecteur JSearch (RapidAPI) — remonte les offres Google for Jobs.

C'est par ce biais que les offres publiées sur LinkedIn, Indeed ou Glassdoor
sont couvertes : ces sites interdisent le scraping direct, mais leurs offres
sont indexées par Google for Jobs, que JSearch expose via une API.

Clé gratuite : https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
→ RAPIDAPI_KEY dans .env (offre gratuite : ~200 requêtes/mois, le connecteur
fait 4 requêtes par scan).
"""
from __future__ import annotations

from ..config import settings
from .base import Connector, ConnectorResult, RawOffer, dedupe_raw, parse_published, profile_queries

SEARCH_URL = "https://jsearch.p.rapidapi.com/search"


class JSearchConnector(Connector):
    name = "jsearch"
    label = "JSearch (LinkedIn / Indeed via Google)"
    needs_key = True

    def is_configured(self) -> bool:
        return bool(settings.rapidapi_key)

    def _parse(self, item: dict) -> RawOffer:
        published = parse_published(item.get("job_posted_at_datetime_utc"))
        city = item.get("job_city") or ""
        country = item.get("job_country") or ""
        location = ", ".join(x for x in [city, country] if x)
        salary = ""
        if item.get("job_min_salary") and item.get("job_max_salary"):
            salary = f"{int(item['job_min_salary'])} - {int(item['job_max_salary'])} {item.get('job_salary_currency') or ''}"
        publisher = item.get("job_publisher") or ""
        desc = item.get("job_description", "") or ""
        if publisher:
            desc = f"[Publiée via {publisher}]\n\n" + desc
        return RawOffer(
            source=self.name,
            source_id=str(item.get("job_id", "")),
            title=item.get("job_title", ""),
            company=item.get("employer_name", ""),
            location=location,
            description=desc,
            url=item.get("job_apply_link", "") or item.get("job_google_link", ""),
            contract_type=(item.get("job_employment_type") or "").replace("FULLTIME", "Temps plein").replace("CONTRACTOR", "Freelance"),
            salary_text=salary,
            remote=bool(item.get("job_is_remote")),
            published_at=published,
        )

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        if not self.is_configured():
            result.errors.append("Clé RAPIDAPI_KEY absente du .env")
            return result

        headers = {
            "X-RapidAPI-Key": settings.rapidapi_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        # 4 requêtes max par scan pour rester dans le quota gratuit RapidAPI.
        keywords = profile_queries(profile)
        queries = [
            {"query": f"{kw} Lyon", "country": "fr", "date_posted": "month"} for kw in keywords[:2]
        ] + [
            {"query": f"{kw} France remote", "country": "fr", "date_posted": "month", "remote_jobs_only": "true"}
            for kw in keywords[:2]
        ]
        with self.client() as client:
            for query in queries:
                params = {"num_pages": "1", "page": "1", **query}
                try:
                    resp = client.get(SEARCH_URL, params=params, headers=headers)
                    resp.raise_for_status()
                    for item in resp.json().get("data", []):
                        result.offers.append(self._parse(item))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Requête {query['query']} : {exc}")

        result.offers = dedupe_raw(result.offers)
        return result
