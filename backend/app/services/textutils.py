"""Utilitaires de normalisation de texte (accents, casse, ponctuation)."""
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


def fingerprint(title: str, company: str) -> str:
    """Empreinte stable d'une offre pour le dédoublonnage entre sources."""
    base = normalize(title) + "|" + normalize(company)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()
