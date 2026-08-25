"""Analyse du marché à partir des offres collectées.

Tout est calculé depuis la base locale : aucune source externe, aucun appel
réseau. L'intérêt est de répondre à des questions concrètes — quelles
compétences reviennent dans les annonces lyonnaises, lesquelles manquent au CV,
qui recrute, à quel salaire.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Offer, Profile
from .cv_parser import SKILL_TAXONOMY
from .textutils import contains_word, normalize

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
