"""Analyse du marché à partir des offres collectées.

Tout est calculé depuis la base locale : aucune source externe, aucun appel
réseau. L'intérêt est de répondre à des questions concrètes — quelles
compétences reviennent dans les annonces lyonnaises, lesquelles manquent au CV,
qui recrute, à quel salaire.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..models import Offer, Profile
from .cv_parser import SKILL_TAXONOMY
from .textutils import canonical_title, contains_word, normalize

# Nombre d'offres minimum pour qu'un classement ait un sens.
MIN_OFFRES = 3


def competences_demandees(db: Session, limite: int = 25) -> dict:
    """Compétences de la taxonomie les plus citées dans les offres collectées.

    Renvoie le classement, avec pour chacune si elle figure déjà dans le CV.
    """
    profile = db.get(Profile, 1)
    du_cv = {normalize(s) for s in (profile.skills or [])} if profile else set()

    compteur: dict[str, int] = {}
    total = 0
    for (titre, description) in db.query(Offer.title, Offer.description).all():
        total += 1
        texte = normalize(f"{titre or ''} {description or ''}")
        for competence in SKILL_TAXONOMY:
            if contains_word(texte, competence):
                compteur[competence] = compteur.get(competence, 0) + 1

    classement = [
        {
            "competence": competence,
            "offres": nombre,
            "part": round(100 * nombre / total) if total else 0,
            "dans_le_cv": any(competence in s or s in competence for s in du_cv),
        }
        for competence, nombre in sorted(compteur.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "total_offres": total,
        "assez_de_donnees": total >= MIN_OFFRES,
        "competences": classement[:limite],
        # Ce qui revient souvent SANS être dans le CV : les priorités de formation.
        "manquantes": [c for c in classement if not c["dans_le_cv"]][:10],
    }


# --- Salaires ---------------------------------------------------------------
# Les annonces écrivent les salaires de façons très variées : « 45 000 - 55 000 €
# / an », « 45K€ à 60K€ », « Annuel de 45000,00 Euros à 55000,00 Euros »,
# « 3 800 € brut mensuel ». On en extrait des montants ANNUELS comparables.
_UNITE = re.compile(r"(k\s*€|k€|\bk\b|€|euros?|eur\b)", re.IGNORECASE)
_NOMBRE = re.compile(r"\d+(?:[\s\u00a0\u202f.]\d{3})*(?:[.,]\d+)?")
_MENSUEL = re.compile(r"(mensuel|par mois|/\s*mois|au mois)", re.IGNORECASE)

# Bornes de plausibilité pour un salaire annuel brut en France (hors extrêmes).
SALAIRE_MIN, SALAIRE_MAX = 15_000, 250_000


def montants_annuels(texte: str) -> list[int]:
    """Montants annuels plausibles trouvés dans un libellé de salaire.

    Sans unité monétaire dans le texte, on ne devine rien : mieux vaut aucune
    donnée qu'un « 2 ans d'expérience » compté comme un salaire.
    """
    if not texte or not _UNITE.search(texte):
        return []
    en_milliers = bool(re.search(r"k\s*€|k€|\bk\b", texte, re.IGNORECASE))
    mensuel = bool(_MENSUEL.search(texte))

    montants = []
    for brut in _NOMBRE.findall(texte):
        nombre = re.sub(r"[\s\u00a0\u202f.](?=\d{3}\b)", "", brut).replace(",", ".")
        try:
            valeur = float(nombre)
        except ValueError:
            continue
        if en_milliers and valeur < 1000:      # « 45K€ », « 45 - 55 K€ »
            valeur *= 1000
        if mensuel and valeur < SALAIRE_MIN:   # « 3 800 € brut mensuel »
            valeur *= 12
        if SALAIRE_MIN <= valeur <= SALAIRE_MAX:
            montants.append(int(round(valeur)))
    return sorted(set(montants))


def _mediane(valeurs: list[int]) -> int | None:
    if not valeurs:
        return None
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) // 2


def qui_recrute(db: Session, limite: int = 20) -> dict:
    """Entreprises qui publient le plus, et salaires observés par intitulé."""
    par_entreprise: dict[str, dict] = {}
    par_titre: dict[str, list[int]] = {}
    avec_salaire = 0

    for titre, entreprise, salaire, score in db.query(
        Offer.title, Offer.company, Offer.salary_text, Offer.final_score
    ).all():
        nom = (entreprise or "").strip() or "Entreprise non précisée"
        entree = par_entreprise.setdefault(nom, {"entreprise": nom, "offres": 0, "scores": []})
        entree["offres"] += 1
        entree["scores"].append(score or 0)

        montants = montants_annuels(salaire or "")
        if montants:
            avec_salaire += 1
            cle = canonical_title(titre or "") or "autre"
            par_titre.setdefault(cle, []).extend(montants)

    entreprises = sorted(
        (
            {
                "entreprise": e["entreprise"],
                "offres": e["offres"],
                "score_moyen": round(sum(e["scores"]) / len(e["scores"]), 1) if e["scores"] else 0,
            }
            for e in par_entreprise.values()
        ),
        key=lambda e: (-e["offres"], e["entreprise"]),
    )

    salaires = sorted(
        (
            {
                "intitule": intitule,
                "offres": len(montants) // 2 or 1,  # une offre donne souvent 2 bornes
                "minimum": min(montants),
                "median": _mediane(montants),
                "maximum": max(montants),
            }
            for intitule, montants in par_titre.items()
        ),
        key=lambda s: -(s["median"] or 0),
    )

    return {
        "entreprises": entreprises[:limite],
        "salaires": salaires[:limite],
        "offres_avec_salaire": avec_salaire,
    }
