"""Utilitaires de normalisation de texte (accents, casse, ponctuation)."""
import difflib
import hashlib
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings


def naif(moment: datetime) -> datetime:
    """Ramène une date à l'heure locale naïve (référentiel unique de l'app)."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(ZoneInfo(settings.timezone)).replace(tzinfo=None)


def parse_iso_dt(value) -> datetime | None:
    """Date ISO (celles de status_history) parsée sans jamais lever.

    Toujours renvoyée en heure locale NAÏVE : une date reçue avec un décalage
    (« 2026-09-01T10:00:00+02:00 ») serait sinon incomparable avec local_now().
    """
    try:
        return naif(datetime.fromisoformat(value))
    except (TypeError, ValueError):
        return None


def normalize(text: str) -> str:
    """Minuscule, sans accents, espaces simples."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9+#./ -]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_word(haystack_norm: str, needle: str) -> bool:
    """Recherche de `needle` (déjà ou non normalisé) comme mot/expression entière."""
    needle_norm = normalize(needle)
    if not needle_norm:
        return False
    # "s?" : un titre français au pluriel ("Responsable Tests", "Ingénieur de
    # Tests") ne matchait jamais une liste au singulier (CORE_TITLES, QA_HINTS)
    # — faux négatif silencieux qui plafonnait à tort des offres QA réelles.
    pattern = r"(?<![a-z0-9])" + re.escape(needle_norm) + r"s?(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def escape_like(value: str) -> str:
    """Échappe les jokers SQL (%, _) d'une saisie utilisateur pour un LIKE/ILIKE.

    À utiliser avec `.ilike(motif, escape="\\\\")`.
    """
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def fingerprint(title: str, company: str) -> str:
    """Empreinte stable d'une offre pour le dédoublonnage entre sources."""
    base = normalize(title) + "|" + normalize(company)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


# Mentions qui ne changent pas le poste : genre, contrat, urgence…
_TITLE_NOISE = re.compile(
    r"\b(h/f|f/h|h-f|f-h|hf|fh|m/f|f/m|m/w|w/m|h/f/x|f/h/x"
    r"|cdi|cdd|interim|freelance|stage|alternance|apprentissage"
    r"|temps plein|temps partiel|urgent|des que possible)\b"
)


def canonical_title(title: str) -> str:
    """Titre réduit à son essence pour la comparaison de doublons."""
    t = normalize(title)
    t = _TITLE_NOISE.sub(" ", t)
    t = re.sub(r"[./#+-]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def titles_similar(a: str, b: str, threshold: float = 0.88) -> bool:
    """Deux intitulés désignent-ils très probablement la même offre ?

    Utilisé uniquement quand l'entreprise est identique : on peut donc être
    exigeant sur le titre sans risquer de fusionner deux postes distincts.
    """
    ca, cb = canonical_title(a), canonical_title(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    if set(ca.split()) == set(cb.split()):
        return True  # mêmes mots, ordre différent
    return difflib.SequenceMatcher(None, ca, cb).ratio() >= threshold


# Télétravail partiel n'est PAS du télétravail complet : le scoring accorde
# 13 points sur 15 au full remote (_location_score, scoring.py) — les compter
# pour un jour par semaine gonflerait le score. Partagé entre tous les points
# d'entrée d'une offre (scan HelloWork/France Travail, ajout manuel) : avant
# extraction ici, seul HelloWork appliquait cette règle, pas les deux autres.
PARTIEL_TELETRAVAIL = ("partiel", "ponctuel", "occasionnel", "hybride", "1 jour", "2 jours", "3 jours")


def teletravail_complet(*textes: str) -> bool:
    """Vrai seulement pour du télétravail TOTAL, jamais pour du partiel.

    Chaque argument est un segment de texte indépendant (ex. plusieurs champs
    d'une carte d'offre) : dès que l'un mentionne « télétravail »/« remote »,
    c'est CE segment qui tranche — « hybride » et « partiel » comptent, pas
    l'absence de ces mots dans un autre segment.
    """
    for texte in textes:
        bas = normalize(texte)
        if "teletravail" in bas or "remote" in bas:
            return not any(mot in bas for mot in PARTIEL_TELETRAVAIL)
    return False


# Caractères par lesquels un tableur interprète une cellule comme une formule.
_DEBUTS_DE_FORMULE = ("=", "+", "-", "@", "\t", "\r")


def cellule_sure(valeur):
    """Neutralise une cellule que le tableur prendrait pour une formule.

    Les titres d'offres viennent du HTML scrapé d'HelloWork et de l'APEC :
    entrée non maîtrisée. Un titre commençant par « = » s'exécute à l'ouverture
    du CSV dans Excel. Le classeur .xlsx a déjà sa protection (offers.py) ;
    ce helper la rend disponible partout.
    """
    if isinstance(valeur, str) and valeur.startswith(_DEBUTS_DE_FORMULE):
        return "'" + valeur
    return valeur
