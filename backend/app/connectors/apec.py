"""Connecteur APEC (best-effort, service web non officiel du site apec.fr).

L'APEC n'a pas d'API publique : ce connecteur appelle le service JSON utilisé
par le site lui-même. Le format peut évoluer ; le parsing est donc défensif et
toute erreur est simplement remontée dans les statistiques du scan.
"""
from __future__ import annotations

from ..config import settings  # noqa: F401  (pas de clé nécessaire, import gardé pour homogénéité)
from .base import Connector, ConnectorResult, RawOffer, dedupe_raw, profile_queries

SEARCH_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"
DETAIL_URL = "https://www.apec.fr/candidat/recherche-emplois.html/emplois/detail-offre/{id}"

# Coordonnées de Lyon pour la recherche géolocalisée.
LYON = {"latitude": 45.7578137, "longitude": 4.8320114}


class ApecConnector(Connector):
    name = "apec"
    label = "APEC"
    needs_key = False

    def _parse(self, item: dict) -> RawOffer | None:
        numero = str(item.get("numeroOffre") or item.get("id") or "")
        title = item.get("intitule") or item.get("titre") or ""
        if not numero or not title:
            return None
        company = item.get("enseigne") or item.get("nomCommercial") or ""
        location = item.get("lieuTexte") or item.get("lieux") or ""
        if isinstance(location, list):
            location = ", ".join(str(x) for x in location)
        desc = item.get("texteOffre") or item.get("descriptif") or ""
        salary = item.get("salaireTexte") or ""
        contract = item.get("typeContrat") or ""
        if isinstance(contract, dict):
            contract = contract.get("libelle", "")
        return RawOffer(
            source=self.name,
            source_id=numero,
            title=str(title),
            company=str(company),
            location=str(location),
            description=str(desc),
            url=DETAIL_URL.format(id=numero),
            contract_type=str(contract),
            salary_text=str(salary),
        )

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        payloads = []
        keywords = profile_queries(profile)
        for kw in keywords[:4]:
            payloads.append(
                {
                    "activeFiltre": True,
                    "motsCles": kw,
                    "pointGeolocDeReference": LYON,
                    "distance": int(profile.get("radius_km", 40)),
                    "pagination": {"range": 50, "startIndex": 0},
                    "sorts": [{"type": "SCORE", "direction": "DESCENDING"}],
                }
            )
        # Recherche nationale télétravail.
        payloads.append(
            {
                "activeFiltre": True,
                "motsCles": f"{keywords[0]} télétravail",
                "pagination": {"range": 50, "startIndex": 0},
                "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
            }
        )

        with self.client() as client:
            for payload in payloads:
                try:
                    resp = client.post(SEARCH_URL, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("resultats") or data.get("offres") or []
                    for item in items:
                        offer = self._parse(item)
                        if offer:
                            result.offers.append(offer)
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Requête « {payload.get('motsCles')} » : {exc}")

        result.offers = dedupe_raw(result.offers)
        if not result.offers and not result.errors:
            result.errors.append("Aucune offre APEC (le format du service a peut-être changé).")
        return result
