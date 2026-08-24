"""Connecteur France Travail (ex Pôle Emploi) — API officielle Offres d'emploi v2.

Clés gratuites sur https://francetravail.io : créer une application, cocher
l'API « Offres d'emploi v2 », puis renseigner FT_CLIENT_ID et FT_CLIENT_SECRET
dans le fichier .env.
"""
from __future__ import annotations

from datetime import datetime

from ..config import settings
from .base import Connector, ConnectorResult, RawOffer, dedupe_raw

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


class FranceTravailConnector(Connector):
    name = "france_travail"
    label = "France Travail"
    needs_key = True

    def is_configured(self) -> bool:
        return bool(settings.ft_client_id and settings.ft_client_secret)

    def _token(self, client) -> str:
        resp = client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.ft_client_id,
                "client_secret": settings.ft_client_secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _parse(self, item: dict) -> RawOffer:
        published = None
        if item.get("dateCreation"):
            try:
                published = datetime.fromisoformat(item["dateCreation"].replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                published = None
        lieu = (item.get("lieuTravail") or {}).get("libelle", "")
        origine = (item.get("origineOffre") or {}).get("urlOrigine", "")
        url = origine or f"https://candidat.francetravail.fr/offres/recherche/detail/{item.get('id', '')}"
        salaire = (item.get("salaire") or {}).get("libelle", "")
        desc = item.get("description", "") or ""
        competences = ", ".join(c.get("libelle", "") for c in (item.get("competences") or []))
        if competences:
            desc += "\n\nCompétences demandées : " + competences
        return RawOffer(
            source=self.name,
            source_id=str(item.get("id", "")),
            title=item.get("intitule", ""),
            company=(item.get("entreprise") or {}).get("nom", ""),
            location=lieu,
            description=desc,
            url=url,
            contract_type=item.get("typeContratLibelle", "") or item.get("typeContrat", ""),
            salary_text=salaire,
            remote="teletravail" in (desc + lieu).lower().replace("é", "e"),
            published_at=published,
        )

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        if not self.is_configured():
            result.errors.append("Clés FT_CLIENT_ID / FT_CLIENT_SECRET absentes du .env")
            return result

        keywords = ["test manager", "QA", "responsable test", "testeur", "quality assurance"]
        with self.client() as client:
            try:
                token = self._token(client)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"Authentification France Travail impossible : {exc}")
                return result
            headers = {"Authorization": f"Bearer {token}"}

            queries: list[dict] = []
            # Autour de Lyon : recherche par département du Rhône.
            for kw in keywords:
                queries.append({"motsCles": kw, "departement": "69", "range": "0-149"})
            # Full remote : recherche nationale avec le mot-clé télétravail.
            for kw in ["test manager télétravail", "QA télétravail"]:
                queries.append({"motsCles": kw, "range": "0-149"})

            for params in queries:
                try:
                    resp = client.get(SEARCH_URL, params=params, headers=headers)
                    if resp.status_code == 204:
                        continue
                    resp.raise_for_status()
                    for item in resp.json().get("resultats", []):
                        result.offers.append(self._parse(item))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Requête {params.get('motsCles')} : {exc}")

        result.offers = dedupe_raw(result.offers)
        return result
