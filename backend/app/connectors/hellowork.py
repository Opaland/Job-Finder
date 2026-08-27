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

from ..services.textutils import normalize
from .base import (
    Connector, ConnectorResult, RawOffer,
    aucune_offre, dedupe_raw, profile_queries, resume_erreur,
)

SEARCH_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html?k={kw}&l={loc}"
# Le télétravail n'est PAS un lieu : « l=Télétravail » répond 200 avec « 0 offre »
# — deux des cinq recherches ne ramenaient donc JAMAIS rien, et sans erreur pour
# le signaler (les recherches lyonnaises, elles, ramenaient des offres). Le site
# a un filtre dédié. Vérifié le 27/08/2026 : « t=Complet » renvoie 15 offres sur
# « test » et 2 sur « qa », toutes en télétravail complet.
REMOTE_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html?k={kw}&t=Complet"
OFFER_RE = re.compile(r"/fr-fr/emplois/(\d+)\.html")

# SOURCE PRINCIPALE : le lien de chaque carte porte tous les champs en clair
# dans son `aria-label`, relevé sur une vraie page le 27/08/2026 :
#   « Voir offre de Test Manager H/F à Lyon 9e - 69, chez Stormshield,
#     pour un CDI, en temps plein, Télétravail partiel »
# C'est infiniment plus solide que de deviner les champs à leur POSITION dans la
# carte : un badge ajouté par le site (« Recruteur actif », « Publiée
# aujourd'hui »…) décalait tout, le titre devenait le badge et l'entreprise
# devenait le titre — sur 100 % des offres, sans que rien ne le signale.
ARIA_RE = re.compile(r"^voir\s+(?:l['’])?offre\s+de\s+(?P<reste>.+)$", re.IGNORECASE | re.DOTALL)
ARIA_CHEZ = ", chez "
ARIA_CONTRAT_RE = re.compile(r", pour une? ")

# REPLI, si le site cesse de fournir l'aria-label : les champs se reconnaissent
# alors à leur forme dans la carte. Textes relevés le 27/08/2026 :
#   ['Suivi de candidature', 'Test Manager H/F', 'Stormshield',
#    'Lyon 9e - 69', 'CDI', 'Télétravail partiel', 'Voir l’offre',
#    'il y a 13 jours']
CONTRATS = {
    "cdi", "cdd", "interim", "freelance", "alternance", "stage",
    "apprentissage", "independant", "cdi interimaire",
}
# « Lyon 9e - 69 », « Villeurbanne - 69 », ou un code postal seul « 69100 ».
# La lettre en tête de la première forme est indispensable : sans elle,
# « 45000 - 60000 € par an » ou « 40 - 69 k€ » passait pour un lieu, l'offre
# perdait ses 15 points de localisation et sortait du digest. La seconde forme
# doit occuper TOUT le texte, pour la même raison.
LIEU_RE = re.compile(r"[^\W\d_].*-\s*\d{2,3}\s*$|^\d{5}$")
# « il y a 13 jours », mais aussi « plus de 1 mois » : HelloWork bascule sur
# cette seconde forme au-delà d'un mois. Elle n'était pas reconnue — l'offre
# perdait sa date, sortait des tranches de fraîcheur du marché, et échappait
# donc à la détection des annonces fantômes, qui vise précisément les vieilles.
PUBLIEE_RE = re.compile(r"(?:il y a|plus de)\s+(\d+)\s*(minute|heure|jour|semaine|mois)", re.IGNORECASE)
JOURS_PAR_UNITE = {"minute": 0, "heure": 0, "jour": 1, "semaine": 7, "mois": 30}
# Dates nommées, comparées après `normalize` (qui remplace l'apostrophe par une
# espace) : « Aujourd'hui » et « aujourd’hui » donnent tous deux « aujourd hui ».
JOURS_NOMMES = {"aujourd hui": 0, "hier": 1}
# Textes d'interface présents dans la carte, qui ne décrivent pas l'offre.
BRUIT = {
    "suivi de candidature", "voir l'offre", "voir l’offre", "nouveau",
    "urgent", "candidature facile", "offre sponsorisée",
}
# Garde-fou de remontée : au-delà on embarquerait la liste entière plutôt qu'une
# carte (cas d'une page à résultat unique, où aucun ancêtre ne contient deux
# offres). Mesuré à 8 niveaux sur la vraie page du 27/08/2026 — la marge est
# volontaire, le site ajoute et retire des conteneurs sans prévenir.
NIVEAUX_MAX = 14
# « Télétravail partiel » n'est PAS du télétravail complet : le scoring accorde
# 13 points sur 15 au full remote, les compter pour un jour par semaine
# gonflerait le score de toutes les offres lyonnaises.
PARTIEL = ("partiel", "ponctuel", "occasionnel", "hybride", "1 jour", "2 jours", "3 jours")


def _teletravail_complet(textes: list[str]) -> bool:
    """Vrai seulement pour du télétravail TOTAL. `normalize` : « Teletravail »
    sans accent et « TÉLÉTRAVAIL » disent la même chose."""
    for texte in textes:
        bas = normalize(texte)
        if "teletravail" in bas or "remote" in bas:
            return not any(mot in bas for mot in PARTIEL)
    return False


def champs_aria(etiquette: str | None) -> dict | None:
    """Décompose l'aria-label d'un lien d'offre, ou None s'il n'a pas ce format.

    Découpage par ancres (« , chez », « , pour un ») plutôt que par une regex
    gourmande : un titre peut lui-même contenir « à » (« Testeur à Lyon H/F »),
    et c'est le DERNIER « à » qui introduit le lieu.
    """
    trouve = ARIA_RE.match((etiquette or "").strip())
    if not trouve:
        return None
    reste = trouve.group("reste")
    if ARIA_CHEZ not in reste:
        return None
    gauche, droite = reste.split(ARIA_CHEZ, 1)
    if " à " not in gauche:
        return None
    titre, lieu = gauche.rsplit(" à ", 1)
    morceaux = ARIA_CONTRAT_RE.split(droite, maxsplit=1)
    segments = [s.strip() for s in (morceaux[1].split(",") if len(morceaux) > 1 else []) if s.strip()]
    return {
        "titre": titre.strip(),
        "lieu": lieu.strip(),
        "entreprise": morceaux[0].strip(),
        "contrat": segments[0] if segments else "",
        "segments": segments,
    }


def _identifiants(noeud) -> set[str]:
    """Identifiants d'offre DISTINCTS présents sous ce noeud.

    Compter les liens serait faux : HelloWork peut très bien mettre deux <a>
    vers la même annonce dans une carte (le titre et un bouton « Voir l'offre »).
    On s'arrêterait alors au parent immédiat, qui ne porte que titre et
    entreprise — lieu, contrat et date vides sur 100 % des offres.
    """
    return {
        trouve.group(1)
        for lien in noeud.find_all("a", href=OFFER_RE)
        if (trouve := OFFER_RE.search(lien.get("href", "")))
    }


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
            if len(_identifiants(parent)) > 1:
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
            # La date n'est PAS dans l'aria-label : elle vient toujours de la carte.
            published_at = self._publiee_le(textes)

            aria = champs_aria(link.get("aria-label"))
            if aria:
                title = aria["titre"]
                company = aria["entreprise"]
                location = aria["lieu"]
                contract = aria["contrat"]
                remote = _teletravail_complet(aria["segments"])
            else:
                if not textes:
                    continue
                title = textes[0]
                location = next((t for t in textes if LIEU_RE.search(t)), "")
                contract = next((t for t in textes if normalize(t) in CONTRATS), "")
                remote = _teletravail_complet(textes)
                # L'entreprise est le premier texte restant une fois retirés le
                # titre et les champs déjà identifiés.
                deja_vus = {title, location, contract}
                company = next(
                    (t for t in textes[1:]
                     if t not in deja_vus and not PUBLIEE_RE.search(t)
                     and "teletravail" not in normalize(t) and len(t) < 80),
                    "",
                )
            if len(title) < 4:
                continue

            # Le salaire n'est pas dans l'aria-label mais bien sur la carte
            # (« 50 000 - 60 000 € / an », « 280 - 300 € / jour ») : le jeter
            # privait le scoring du seul chiffre que HelloWork donne.
            salary = next((t for t in textes if "€" in t), "")

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
                    salary_text=salary,
                    remote=remote,
                    published_at=published_at,
                )
            )
        return offers

    @staticmethod
    def _publiee_le(textes: list[str]):
        """« il y a 13 jours », « plus de 1 mois », « hier » → date approchée."""
        from datetime import timedelta

        from ..models import local_now

        for texte in textes:
            trouve = PUBLIEE_RE.search(texte)
            if trouve:
                nombre, unite = int(trouve.group(1)), trouve.group(2).lower()
                return local_now() - timedelta(days=nombre * JOURS_PAR_UNITE.get(unite, 0))
            if normalize(texte) in JOURS_NOMMES:
                return local_now() - timedelta(days=JOURS_NOMMES[normalize(texte)])
        return None

    @staticmethod
    def recherches(profile: dict) -> list[tuple[str, str]]:
        """Les URL interrogées, sans rien appeler : (libellé, URL).

        Fonction pure, donc vérifiable sans réseau ET sans client bouchonné.
        C'est ici que se joue la distinction entre le LIEU et le FILTRE
        télétravail — confondre les deux vidait deux recherches sur cinq.
        """
        keywords = profile_queries(profile)
        return [
            (f"{kw} / Lyon", SEARCH_URL.format(kw=quote_plus(kw), loc=quote_plus("Lyon")))
            for kw in keywords[:3]
        ] + [
            (f"{kw} / télétravail complet", REMOTE_URL.format(kw=quote_plus(kw)))
            for kw in keywords[:2]
        ]

    def fetch(self, profile: dict) -> ConnectorResult:
        result = ConnectorResult()
        with self.client() as client:
            for libelle, url in self.recherches(profile):
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    result.offers.extend(self._parse_page(resp.text))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"Recherche « {libelle} » : {resume_erreur(exc)}")

        result.offers = dedupe_raw(result.offers)
        if not result.offers and not result.errors:
            result.errors.append(aucune_offre("la structure du site HelloWork a probablement changé."))
        return result
