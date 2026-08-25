"""Utilitaires de normalisation de texte (accents, casse, ponctuation)."""
import difflib
import hashlib
import re
import unicodedata


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
    pattern = r"(?<![a-z0-9])" + re.escape(needle_norm) + r"(?![a-z0-9])"
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
