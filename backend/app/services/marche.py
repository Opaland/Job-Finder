"""Analyse du marché à partir des offres collectées.

Tout est calculé depuis la base locale : aucune source externe, aucun appel
réseau. L'intérêt est de répondre à des questions concrètes — quelles
compétences reviennent dans les annonces lyonnaises, lesquelles manquent au CV,
qui recrute, à quel salaire.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..models import STATUTS_CLOS, Offer, Profile, local_now
from .cv_parser import SKILL_TAXONOMY
from .textutils import canonical_title, normalize

# Nombre d'offres minimum pour qu'un classement ait un sens.
MIN_OFFRES = 3

# Une seule expression régulière pour toute la taxonomie : chercher les ~110
# compétences une par une coûtait une trentaine de secondes sur 2 000 offres.
_COMPETENCES = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(normalize(c)) for c in
                                 sorted(SKILL_TAXONOMY, key=len, reverse=True)) + r")(?![a-z0-9])"
)


def competences_citees(texte_normalise: str) -> set[str]:
    """Compétences de la taxonomie présentes dans un texte déjà normalisé."""
    return set(_COMPETENCES.findall(texte_normalise))


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
        for competence in competences_citees(normalize(f"{titre or ''} {description or ''}")):
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
    par_titre: dict[str, dict] = {}
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
            entree_titre = par_titre.setdefault(cle, {"montants": [], "offres": 0})
            entree_titre["montants"].extend(montants)
            entree_titre["offres"] += 1   # une offre, quel que soit le nombre de bornes lues

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
                "offres": donnees["offres"],
                "minimum": min(donnees["montants"]),
                "median": _mediane(donnees["montants"]),
                "maximum": max(donnees["montants"]),
            }
            for intitule, donnees in par_titre.items()
        ),
        key=lambda s: -(s["median"] or 0),
    )

    return {
        "entreprises": entreprises[:limite],
        "salaires": salaires[:limite],
        "offres_avec_salaire": avec_salaire,
    }


# --- Ce que l'IA a repéré comme manquant ------------------------------------

def manques_recurrents(db: Session, limite: int = 15) -> dict:
    """Compétences citées comme manquantes dans les analyses d'écart de l'IA.

    L'IA écrit ces analyses en texte libre : on ne cherche donc pas à
    l'interpréter, on compte les compétences de la taxonomie qui apparaissent
    dans une analyse ALORS qu'elles sont absentes du CV.
    """
    profile = db.get(Profile, 1)
    du_cv = {normalize(s) for s in (profile.skills or [])} if profile else set()

    compteur: dict[str, int] = {}
    analyses = 0
    for (analyse,) in db.query(Offer.gap_analysis).filter(Offer.gap_analysis.isnot(None)).all():
        texte = normalize(analyse or "")
        if not texte:
            continue
        analyses += 1
        for competence in competences_citees(texte):
            if any(competence in s or s in competence for s in du_cv):
                continue
            compteur[competence] = compteur.get(competence, 0) + 1

    return {
        "analyses": analyses,
        "manques": [
            {"competence": c, "citee_dans": n}
            for c, n in sorted(compteur.items(), key=lambda kv: (-kv[1], kv[0]))
        ][:limite],
    }


# --- Fraîcheur et annonces fantômes -----------------------------------------

# Au-delà de ce délai depuis la publication, une offre encore en ligne est
# probablement republiée en boucle (ESN qui entretient un vivier).
FANTOME_APRES_JOURS = 60


def fraicheur(db: Session, limite: int = 20) -> dict:
    """Répartition des offres ouvertes par ancienneté + annonces suspectes."""
    maintenant = local_now()
    tranches = {"0-7": 0, "8-30": 0, "31-60": 0, "60+": 0, "inconnue": 0}
    fantomes = []

    for oid, titre, entreprise, publiee, collectee, en_ligne, statut, score, url in db.query(
        Offer.id, Offer.title, Offer.company, Offer.published_at, Offer.collected_at,
        Offer.still_online, Offer.status, Offer.final_score, Offer.url,
    ).filter(Offer.status.notin_(STATUTS_CLOS)).all():
        if publiee is None:
            tranches["inconnue"] += 1
            continue
        jours = (maintenant - publiee).days
        if jours <= 7:
            tranches["0-7"] += 1
        elif jours <= 30:
            tranches["8-30"] += 1
        elif jours <= 60:
            tranches["31-60"] += 1
        else:
            tranches["60+"] += 1
            if en_ligne:
                fantomes.append({
                    "id": oid, "title": titre, "company": entreprise, "url": url,
                    "final_score": score, "jours": jours, "status": statut,
                })

    fantomes.sort(key=lambda f: -f["jours"])
    return {
        "tranches": [{"tranche": t, "offres": n} for t, n in tranches.items()],
        "seuil_fantome_jours": FANTOME_APRES_JOURS,
        "fantomes": fantomes[:limite],
    }
