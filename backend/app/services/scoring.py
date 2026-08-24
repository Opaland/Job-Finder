"""Moteur de classement des offres par rapport au profil.

Le score (0-100) est déterministe et explicable. Il est ensuite éventuellement
affiné par l'IA locale (Claude Code CLI) pour les meilleures offres.

Barème :
  - Adéquation du poste (titre)        : 0 à 40
  - Compétences en commun avec le CV   : 0 à 25
  - Niveau / séniorité                 : 0 à 10
  - Localisation (Lyon / remote)       : 0 à 15
  - Type de contrat                    : 0 à 5
  - Secteur déjà pratiqué              : 0 à 5

Un poste clairement hors QA ou junior/stage voit son score plafonné.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .textutils import contains_word, normalize

# Titres qui correspondent au métier actuel de Cédric : score maximal.
CORE_TITLES = [
    "test manager", "qa manager", "qa lead", "lead qa", "test lead",
    "responsable test", "responsable des tests", "responsable qa",
    "responsable qualite logicielle", "responsable qualite logiciel",
    "head of qa", "head of quality", "directeur qa", "director qa",
    "quality assurance manager", "manager qa", "quality manager",
    "responsable validation", "test center", "tcoe", "coach test", "coach qa",
]

# Postes QA proches mais pas identiques au poste actuel.
NEAR_TITLES = [
    "qa engineer", "ingenieur qa", "ingenieur test", "ingenieur de test",
    "quality assurance", "automaticien", "qa automation", "automation engineer",
    "testeur", "test analyst", "analyste de test", "analyste test",
    "consultant test", "consultant qa", "expert test", "expert qa",
    "release manager", "quality engineer", "sdet", "test automation",
]

# Indices QA génériques (dans le titre ou la description).
QA_HINTS = ["qa", "test", "testing", "qualite logicielle", "quality assurance", "recette", "homologation"]

MANAGEMENT_HINTS = [
    "management", "manager", "encadrement", "pilotage", "equipe", "team lead",
    "leadership", "gouvernance", "strategie de test", "roadmap", "recrutement",
]

JUNIOR_FLAGS = ["junior", "stage", "stagiaire", "alternance", "alternant", "apprenti", "apprentissage", "internship", "intern "]

REMOTE_HINTS = [
    "full remote", "100% remote", "100 % remote", "full-remote", "teletravail complet",
    "teletravail total", "remote", "teletravail",
]

# Pondérations par défaut (modifiables dans Profil & CV). Le score final est
# toujours ramené sur 100, quel que soit le total des pondérations.
DEFAULT_WEIGHTS = {
    "titre": 40,
    "competences": 25,
    "seniorite": 10,
    "localisation": 15,
    "contrat": 5,
    "secteur": 5,
}
# Barème interne de chaque critère (l'échelle sur laquelle les fonctions notent).
_BASE_MAX = dict(DEFAULT_WEIGHTS)


@dataclass
class ScoreResult:
    score: float = 0.0
    breakdown: list[dict] = field(default_factory=list)

    def add(self, label: str, points: float, maximum: float, detail: str):
        self.breakdown.append(
            {"label": label, "points": round(points, 1), "max": maximum, "detail": detail}
        )
        self.score += points


def _title_score(title_norm: str, desc_norm: str, target_titles: list[str]) -> tuple[float, str]:
    for t in [normalize(x) for x in target_titles] + CORE_TITLES:
        if t and contains_word(title_norm, t):
            return 40, f"Intitulé « {t} » : c'est le métier que tu exerces déjà."
    for t in NEAR_TITLES:
        if contains_word(title_norm, t):
            return 26, f"Intitulé proche de ton métier ({t})."
    if any(contains_word(title_norm, h) for h in QA_HINTS):
        return 16, "Le titre mentionne le test / la QA sans être un poste de management."
    if any(contains_word(desc_norm, h) for h in QA_HINTS):
        return 6, "Le poste n'est pas un poste QA, mais la description parle de test/qualité."
    return 0, "Poste hors du domaine QA/test."


def _skills_score(desc_norm: str, title_norm: str, skills: list[str]) -> tuple[float, str]:
    text = title_norm + " " + desc_norm
    hits = [s for s in skills if contains_word(text, s)]
    # Rendement décroissant : 1 compétence = ~5 pts, 4 = ~15, 9+ = 25.
    points = min(25.0, 25.0 * math.sqrt(len(hits)) / 3.0)
    if hits:
        shown = ", ".join(hits[:8]) + ("…" if len(hits) > 8 else "")
        return points, f"{len(hits)} compétence(s) de ton CV citée(s) : {shown}"
    return 0, "Aucune compétence de ton CV citée dans l'offre."


def _seniority_score(title_norm: str, desc_norm: str) -> tuple[float, str, bool]:
    junior = any(h in title_norm for h in JUNIOR_FLAGS)
    if junior:
        return 0, "Poste junior / stage / alternance : en dessous de ton niveau.", True
    text = title_norm + " " + desc_norm
    mgmt_hits = sum(1 for h in MANAGEMENT_HINTS if contains_word(text, h))
    senior = contains_word(text, "senior") or contains_word(text, "confirme") or contains_word(text, "expert")
    if mgmt_hits >= 2:
        return 10, "Dimension management/pilotage explicite : aligné avec tes 15 ans d'expérience.", False
    if mgmt_hits == 1 or senior:
        return 7, "Poste senior ou avec une part de pilotage.", False
    return 4, "Niveau non précisé dans l'offre.", False


def _location_score(
    location_norm: str, desc_norm: str, title_norm: str,
    location_keywords: list[str], remote_ok: bool, remote_flag: bool,
) -> tuple[float, str]:
    local = any(contains_word(location_norm, normalize(k)) for k in location_keywords if k)
    text = location_norm + " " + desc_norm + " " + title_norm
    remote = remote_flag or any(h in text for h in [normalize(r) for r in REMOTE_HINTS[:6]])
    partial_remote = any(contains_word(text, h) for h in ["teletravail", "remote", "hybride"])
    if local:
        return 15, "Poste dans ta zone (Lyon et alentours)."
    if remote and remote_ok:
        return 13, "Poste en télétravail complet : compatible avec ta recherche."
    aura = any(contains_word(location_norm, z) for z in ["rhone", "ain", "isere", "loire", "auvergne", "rhone-alpes", "69", "38", "42", "01"])
    if aura:
        return 8, "Poste dans la région Auvergne-Rhône-Alpes (au-delà du rayon souhaité)."
    if partial_remote and remote_ok:
        return 6, "Télétravail partiel mentionné, mais poste hors de ta zone."
    if not location_norm:
        return 5, "Localisation non précisée dans l'offre."
    return 1, "Poste hors de ta zone géographique, sans télétravail complet."


def _contract_score(contract_norm: str, desc_norm: str, contracts: list[str]) -> tuple[float, str]:
    wanted = [normalize(c) for c in contracts]
    text = contract_norm + " " + desc_norm
    if contains_word(text, "cdi") and any("cdi" in w for w in wanted):
        return 5, "CDI : correspond à ta recherche."
    if any(contains_word(text, k) for k in ["freelance", "independant", "portage", "mission"]) and any(
        w in ("freelance", "freelance / portage", "portage", "independant") or "freelance" in w for w in wanted
    ):
        return 5, "Mission freelance / portage : correspond à ta recherche."
    if contains_word(text, "cdd") or contains_word(text, "interim"):
        return 2, "CDD/intérim : pas ton premier choix."
    if not contract_norm:
        return 3, "Type de contrat non précisé."
    return 2, "Type de contrat différent de ta recherche."


def _sector_score(text_norm: str, sector_bonus: list[str]) -> tuple[float, str]:
    hits = [s for s in sector_bonus if contains_word(text_norm, normalize(s))]
    if hits:
        return 5, f"Secteur que tu connais déjà : {', '.join(hits[:4])}."
    return 2, "Secteur nouveau pour toi (ta recherche reste ouverte à tous les secteurs)."


def score_offer(offer: dict, profile: dict) -> ScoreResult:
    """Calcule le score d'une offre (dict normalisé) contre le profil (dict).

    Chaque critère note sur son barème interne, puis est mis à l'échelle des
    pondérations du profil ; le total est ramené sur 100.
    """
    res = ScoreResult()
    weights = {**DEFAULT_WEIGHTS, **{k: v for k, v in (profile.get("scoring_weights") or {}).items() if k in DEFAULT_WEIGHTS}}
    total_weight = sum(weights.values()) or 1
    # Chaque critère est ramené à sa part sur 100 : le détail affiché somme
    # toujours au score final, quel que soit le total des pondérations.
    scale = 100.0 / total_weight

    def add_weighted(key: str, label: str, pts: float, why: str):
        share = weights[key] * scale
        scaled = pts * share / _BASE_MAX[key] if _BASE_MAX[key] else 0
        res.add(label, scaled, round(share, 1), why)

    title_norm = normalize(offer.get("title", ""))
    desc_norm = normalize(offer.get("description", ""))
    location_norm = normalize(offer.get("location", ""))
    contract_norm = normalize(offer.get("contract_type", ""))
    full_norm = " ".join([title_norm, desc_norm, location_norm])

    excluded = [normalize(k) for k in profile.get("excluded_keywords", []) if k]
    excluded_hit = next((k for k in excluded if k and contains_word(full_norm, k)), None)

    pts, why = _title_score(title_norm, desc_norm, profile.get("target_titles", []))
    add_weighted("titre", "Adéquation du poste", pts, why)
    qa_score = pts

    pts, why = _skills_score(desc_norm, title_norm, profile.get("skills", []))
    add_weighted("competences", "Compétences du CV", pts, why)

    pts, why, is_junior = _seniority_score(title_norm, desc_norm)
    add_weighted("seniorite", "Niveau / séniorité", pts, why)

    pts, why = _location_score(
        location_norm, desc_norm, title_norm,
        profile.get("location_keywords", []), profile.get("remote_ok", True),
        bool(offer.get("remote")),
    )
    add_weighted("localisation", "Localisation", pts, why)

    pts, why = _contract_score(contract_norm, desc_norm, profile.get("contracts", []))
    add_weighted("contrat", "Contrat", pts, why)

    pts, why = _sector_score(full_norm, profile.get("sector_bonus", []))
    add_weighted("secteur", "Secteur", pts, why)

    # Plafonds : hors QA ou junior, l'offre reste listée mais ne peut pas être bien classée.
    if qa_score == 0:
        res.score = min(res.score, 20)
        res.breakdown.append(
            {"label": "Plafond", "points": 0, "max": 0,
             "detail": "Score plafonné à 20 : poste hors QA/test."}
        )
    elif is_junior:
        res.score = min(res.score, 30)
        res.breakdown.append(
            {"label": "Plafond", "points": 0, "max": 0,
             "detail": "Score plafonné à 30 : poste junior/stage/alternance."}
        )
    if excluded_hit:
        res.score = min(res.score, 10)
        res.breakdown.append(
            {"label": "Mot-clé exclu", "points": 0, "max": 0,
             "detail": f"Score plafonné à 10 : contient « {excluded_hit} » (mot-clé exclu dans ton profil)."}
        )

    res.score = round(min(100.0, max(0.0, res.score)), 1)
    return res


def combined_score(rule_score: float, ai_score: float | None) -> float:
    """Score final : moyenne règles/IA quand l'IA a donné un avis."""
    if ai_score is None:
        return round(rule_score, 1)
    return round(0.5 * rule_score + 0.5 * ai_score, 1)
