"""Connecteur APEC (best-effort, service web non officiel du site apec.fr).

L'APEC n'a pas d'API publique : ce connecteur appelle le service JSON utilisé
par le site lui-même. Le format peut évoluer ; le parsing est donc défensif et
toute erreur est simplement remontée dans les statistiques du scan.
"""
from __future__ import annotations

from ..config import settings  # noqa: F401  (pas de clé nécessaire, import gardé pour homogénéité)
from .base import (
    Connector, ConnectorResult, RawOffer,
    aucune_offre, dedupe_raw, parse_published, profile_queries, resume_erreur,
)

SEARCH_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"
# Au SINGULIER : la forme au pluriel (« recherche-emplois / emplois ») renvoie
# un 404. Chaque offre APEC portait donc un lien mort — vérifié le 27/08/2026.
DETAIL_URL = "https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{id}"

# Coordonnées de Lyon pour la recherche géolocalisée.
# L'APEC filtre par DÉPARTEMENT (champ « lieux »), pas par rayon. Vérifié sur
# l'API réelle le 27/08/2026 :
#   - `distance` fait répondre HTTP 500, quelle que soit la valeur ;
#   - `pointGeolocDeReference` seul est ignoré : une recherche « Lyon » renvoyait
#     Nantes, Saran et Annemasse (1 offre sur 20 dans le Rhône) ;
#   - `lieux: ["69"]` renvoie 20 offres sur 20 dans le Rhône.
# Départements du bassin lyonnais, cohérents avec la zone reconnue par le
# scoring (services/scoring.py, `_location_score`).
DEPARTEMENTS_LYON = ["69", "01", "38", "42"]

# `typeContrat` est un CODE numérique, pas un libellé : injecté tel quel, il
# donnait un contrat « 101888 » que le scoring ne reconnaissait pas (2 points au
# lieu des 5 d'un CDI recherché). Correspondances établies sur ~600 offres
# réelles du bassin lyonnais le 27/08/2026, en croisant le code avec l'intitulé :
#   101888 → CDI (535 intitulés) ; 101887 → CDD (14, dont « CDD - Ingénieur… ») ;
#   597137 → 25 intitulés sur 26 disent « en alternance » ; 597139 → 3 sur 3.
# Deux codes restent inconnus faute d'échantillon parlant : 101889 (7 intitulés,
# aucun en alternance — probablement intérim ou mission) et 597138 (1 seul).
# Un code inconnu laisse le contrat VIDE — « non précisé » est plus juste qu'une
# valeur inventée.
CONTRATS_APEC = {
    "101888": "CDI", "101887": "CDD",
    "597137": "Alternance", "597139": "Alternance",
}


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
        contract = CONTRATS_APEC.get(str(contract), "" if str(contract).isdigit() else str(contract))
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
            # L'API donne la date : sans elle, toutes les offres paraissaient
            # publiées à l'instant, et le tri « les plus récentes » ne triait rien.
            published_at=parse_published(item.get("datePublication") or item.get("dateValidation")),
        )

    @staticmethod
    def payloads(profile: dict) -> list[dict]:
        """Les requêtes envoyées à l'APEC, sans rien appeler.

        Fonction pure, donc vérifiable sans réseau ET sans client bouchonné :
        c'est ici que se joue le filtre géographique, la partie qui a déjà
        régressé une fois (une recherche « Lyon » renvoyait Nantes).
        """
        keywords = profile_queries(profile)
        requetes = [
            {
                "activeFiltre": True,
                "motsCles": kw,
                "lieux": DEPARTEMENTS_LYON,
                "pagination": {"range": 50, "startIndex": 0},
                "sorts": [{"type": "SCORE", "direction": "DESCENDING"}],
            }
            for kw in keywords[:4]
        ]
        # Recherche nationale télétravail : pas de « lieux », c'est volontaire.
        requetes.append(
            {
                "activeFiltre": True,
                "motsCles": f"{keywords[0]} télétravail",
                "pagination": {"range": 50, "startIndex": 0},
                "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
            }
        )
        return requetes

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        with self.client() as client:
            for payload in self.payloads(profile):
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
                    result.errors.append(f"Requête « {payload.get('motsCles')} » : {resume_erreur(exc)}")

        result.offers = dedupe_raw(result.offers)
        if not result.offers and not result.errors:
            result.errors.append(aucune_offre("le format du service APEC a peut-être changé."))
        return result
