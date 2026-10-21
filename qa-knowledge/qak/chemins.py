"""Emplacements des fichiers. Tout est relatif à la racine qa-knowledge/ ;
QAK_RACINE permet de pointer ailleurs (tests, seconde bibliothèque)."""
import os
from pathlib import Path

RACINE = Path(os.environ.get("QAK_RACINE") or Path(__file__).resolve().parent.parent)
CODE = Path(__file__).resolve().parent.parent  # référentiels versionnés livrés avec le code


def racine() -> Path:
    return Path(os.environ.get("QAK_RACINE") or RACINE)


def sources() -> Path:
    return racine() / "bibliotheque" / "sources"


def manifeste() -> Path:
    return racine() / "bibliotheque" / "manifeste.json"


def index_db() -> Path:
    return racine() / "bibliotheque" / "index.db"


def base_db() -> Path:
    return racine() / "connaissances" / "base.db"


def connaissances_jsonl() -> Path:
    return racine() / "connaissances" / "connaissances.jsonl"


def journal_jsonl() -> Path:
    return racine() / "connaissances" / "journal.jsonl"


def taxonomie() -> Path:
    # La taxonomie évolue avec la base : elle suit la racine de données.
    p = racine() / "referentiel" / "taxonomie.json"
    return p if p.exists() else CODE / "referentiel" / "taxonomie.json"


def thesaurus() -> Path:
    p = racine() / "referentiel" / "thesaurus.json"
    return p if p.exists() else CODE / "referentiel" / "thesaurus.json"


def catalogue() -> Path:
    return CODE / "catalogue" / "istqb.json"
