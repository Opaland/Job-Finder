"""Diagnostic des sources d'emploi : que ramène réellement chaque connecteur ?

Écrit pour la validation V1. Le danger d'un connecteur n'est pas qu'il plante —
c'est qu'il réussisse à vide : la source répond, le scan se termine, et l'offre
arrive sans entreprise ni description parce qu'un champ a été renommé. Un scan
normal affiche « 0 nouvelle offre » et tout a l'air normal.

Ce module répond à trois questions par source, en une commande :
  1. la source répond-elle (et sinon, pourquoi, en français) ;
  2. combien d'offres, et à quoi ressemble la première ;
  3. **quels champs sont vides sur TOUTES les offres** — la signature d'un
     mapping cassé, invisible autrement.

`--brut` fige en plus les réponses réelles sur le disque : c'est la matière
première des fixtures de non-régression réclamées par V1.
"""
from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path

from ..connectors import ALL_CONNECTORS
from ..connectors.base import AUCUNE_OFFRE, capture_reponses, resume_erreur

logger = logging.getLogger("jobfinder.diagnostic")

# Champs d'une RawOffer dont l'absence généralisée trahit un mapping cassé.
CHAMPS_ATTENDUS = ["title", "company", "location", "description", "url", "source_id"]
# Manquent légitimement chez certaines sources : signalés pour information, jamais
# comme une alerte. `remote` n'y figure pas : c'est un booléen, et « aucune offre
# en télétravail » est un résultat normal, pas un champ absent.
CHAMPS_FACULTATIFS = ["contract_type", "salary_text", "published_at"]


def _vide(valeur) -> bool:
    """Un champ « vide » au sens du diagnostic : None ou chaîne blanche.

    `False` n'est pas vide — sans quoi `remote` serait signalé à chaque scan
    d'une recherche lyonnaise sans télétravail.
    """
    if valeur is None:
        return True
    return isinstance(valeur, str) and not valeur.strip()


def diagnostiquer_source(connector, profile: dict) -> dict:
    """Interroge une source et décrit ce qu'elle a renvoyé.

    Ne lève jamais : comme `fetch()`, tout part dans `erreurs`.
    """
    resultat = {
        "source": connector.name,
        "label": connector.label,
        "configure": connector.is_configured(),
        "offres": 0,
        "erreurs": [],
        "champs_vides": [],
        "champs_facultatifs_vides": [],
        "exemple": None,
    }
    try:
        reponse = connector.fetch(profile)
    except Exception as exc:  # noqa: BLE001 — un connecteur ne doit jamais lever
        logger.exception("Connecteur %s en erreur pendant le diagnostic", connector.name)
        resultat["erreurs"].append(f"Exception inattendue : {resume_erreur(exc)}")
        return resultat

    resultat["erreurs"] = list(reponse.errors)
    resultat["offres"] = len(reponse.offers)
    if not reponse.offers:
        return resultat

    offres = [asdict(o) for o in reponse.offers]
    resultat["exemple"] = offres[0]
    resultat["champs_vides"] = [
        champ for champ in CHAMPS_ATTENDUS if all(_vide(o.get(champ)) for o in offres)
    ]
    resultat["champs_facultatifs_vides"] = [
        champ for champ in CHAMPS_FACULTATIFS if all(_vide(o.get(champ)) for o in offres)
    ]
    return resultat


def diagnostiquer(
    profile: dict,
    sources: list[str] | None = None,
    capture: Path | None = None,
) -> list[dict]:
    """Diagnostic de toutes les sources (ou seulement de celles nommées).

    `capture` : dossier où figer les réponses brutes — un sous-dossier par
    source, sinon les réponses des six connecteurs se mélangent et ne servent
    plus de fixtures relisibles.
    """
    connecteurs = [c for c in ALL_CONNECTORS if not sources or c.name in sources]
    resultats = []
    for connecteur in connecteurs:
        contexte = capture_reponses(capture / connecteur.name) if capture else nullcontext()
        with contexte:
            resultats.append(diagnostiquer_source(connecteur, profile))
    return resultats


def verdict(resultat: dict) -> tuple[str, str]:
    """(état, explication en français) d'une source diagnostiquée.

    L'état vaut « ok », « suspect » ou « ko » — « suspect » est le cas qui
    compte : la source a répondu, mais ce qu'elle renvoie est inexploitable.
    """
    if not resultat["configure"]:
        # Le connecteur nomme lui-même les variables manquantes : plus utile
        # qu'un message générique.
        detail = resultat["erreurs"][0] if resultat["erreurs"] else "clé absente du .env"
        return "ko", f"Source non configurée — {detail}"
    # Un connecteur qui n'a rien extrait le signale lui-même : ce n'est pas une
    # panne, et ça ne doit pas être classé avec les échecs réseau.
    pannes = [e for e in resultat["erreurs"] if AUCUNE_OFFRE not in e]
    if pannes and not resultat["offres"]:
        return "ko", pannes[0]
    if not resultat["offres"]:
        precision = next((e for e in resultat["erreurs"] if AUCUNE_OFFRE in e), "")
        return "suspect", (
            "La source a répondu sans erreur mais n'a renvoyé aucune offre : "
            "requête trop restrictive, ou format de réponse changé."
            + (f" ({precision})" if precision else "")
        )
    if resultat["champs_vides"]:
        return "suspect", (
            "Champs vides sur toutes les offres : "
            + ", ".join(resultat["champs_vides"])
            + " — le mapping du connecteur ne correspond plus à la réponse."
        )
    if resultat["erreurs"]:
        return "ok", f"{resultat['offres']} offre(s), mais {len(resultat['erreurs'])} erreur(s) partielle(s)."
    return "ok", f"{resultat['offres']} offre(s), tous les champs essentiels remplis."


ETIQUETTES = {"ok": "[ OK      ]", "suspect": "[ SUSPECT ]", "ko": "[ KO      ]"}


def rapport_texte(resultats: list[dict]) -> str:
    """Rapport lisible dans un terminal (et copiable dans une conversation)."""
    lignes = []
    compte = {"ok": 0, "suspect": 0, "ko": 0}

    for resultat in resultats:
        etat, explication = verdict(resultat)
        compte[etat] += 1
        lignes.append(f"{ETIQUETTES[etat]} {resultat['label']}")
        lignes.append(f"             {explication}")

        exemple = resultat["exemple"]
        if exemple:
            lignes.append(f"             1re offre : « {exemple['title']} »"
                          f" — {exemple['company'] or 'ENTREPRISE VIDE'}"
                          f" — {exemple['location'] or 'LIEU VIDE'}")
            description = (exemple.get("description") or "").strip()
            lignes.append(f"             description : {len(description)} caractère(s)"
                          + ("  ← vide, l'IA et le score n'auront rien à lire" if not description else ""))
            if resultat["champs_facultatifs_vides"]:
                lignes.append("             champs facultatifs absents : "
                              + ", ".join(resultat["champs_facultatifs_vides"]))
        # Le verdict reprend déjà la première erreur : on n'affiche que les suivantes.
        for erreur in resultat["erreurs"][1:3]:
            lignes.append(f"             ! {erreur}")
        if len(resultat["erreurs"]) > 3:
            lignes.append(f"             … et {len(resultat['erreurs']) - 3} autre(s) erreur(s)")
        lignes.append("")

    lignes.append(f"Bilan : {compte['ok']} source(s) OK, {compte['suspect']} suspecte(s), "
                  f"{compte['ko']} en échec.")
    if compte["suspect"]:
        lignes.append("Une source « suspecte » est le cas à traiter en priorité : elle ne fait pas de "
                      "bruit, elle fait juste manquer des offres.")
    return "\n".join(lignes)
