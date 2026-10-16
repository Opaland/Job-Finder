"""Sauvegarde et restauration de la base SQLite.

Sprint 49 : logique extraite de `routers/stats.py`, qui n'a par ailleurs rien
à voir avec des statistiques — ce fichier grossissait sans rapport avec son
propos.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from ..database import ensure_schema, engine
from ..models import local_now

# Colonnes sans lesquelles une base restaurée rendrait l'application inutilisable.
COLONNES_INDISPENSABLES = {"id", "fingerprint", "source", "source_id", "title", "collected_at"}
COPIES_DE_SECURITE_GARDEES = 3


class SauvegardeInvalide(Exception):
    """Fichier téléversé refusé — message français affichable tel quel dans l'UI."""


def creer_sauvegarde(db_path: str) -> bytes:
    """Copie cohérente de la base SQLite (API backup, sûre même en cours d'écriture)."""
    src = sqlite3.connect(db_path)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        dest = sqlite3.connect(tmp_path)
        with dest:
            src.backup(dest)
        dest.close()
        return Path(tmp_path).read_bytes()
    finally:
        src.close()
        Path(tmp_path).unlink(missing_ok=True)


def restaurer(content: bytes, db_path: Path) -> dict:
    """Remplace la base par une sauvegarde téléversée (copie de sécurité créée avant)."""
    if not content.startswith(b"SQLite format 3\x00"):
        raise SauvegardeInvalide(
            "Ce fichier n'est pas une base SQLite — choisis un fichier .db issu du bouton de sauvegarde.")

    # Validation du contenu avant de toucher à quoi que ce soit.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        check = sqlite3.connect(tmp_path)
        try:
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"offers", "profile"} <= tables:
                raise SauvegardeInvalide(
                    "Cette base n'est pas une sauvegarde Job Finder (tables offres/profil absentes).")
            # Les noms de tables ne suffisent pas : une base étrangère ayant par
            # hasard une table « offers » était acceptée, migrée, et laissait
            # toutes les pages en erreur 500 sans issue depuis l'interface.
            colonnes = {row[1] for row in check.execute("PRAGMA table_info(offers)")}
            manquantes = COLONNES_INDISPENSABLES - colonnes
            if manquantes:
                raise SauvegardeInvalide(
                    "Cette base a bien une table « offers » mais pas le bon format "
                    f"(colonnes manquantes : {', '.join(sorted(manquantes))}). "
                    "Choisis un fichier issu du bouton de sauvegarde de l'application.",
                )
            offer_count = check.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        except sqlite3.DatabaseError:
            raise SauvegardeInvalide("Fichier SQLite illisible ou corrompu — restauration annulée.")
        finally:
            check.close()

        # Copie de sécurité de la base actuelle, puis restauration via l'API
        # backup de SQLite : le remplacement se fait page à page sous verrou
        # d'écriture, une requête concurrente voit toujours une base cohérente
        # (jamais un fichier à moitié écrit).
        safety_name = f"avant_restauration_{local_now().strftime('%Y-%m-%d_%H%M%S')}.db"
        if db_path.exists():
            current = sqlite3.connect(db_path)
            safety = sqlite3.connect(db_path.parent / safety_name)
            try:
                with safety:
                    current.backup(safety)
            finally:
                safety.close()
                current.close()

        src = sqlite3.connect(tmp_path)
        dest = sqlite3.connect(db_path)
        try:
            with dest:
                src.backup(dest)
        finally:
            dest.close()
            src.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Les copies de sécurité contiennent CV, lettres et notes : n'en garder que
    # quelques-unes évite d'en semer indéfiniment dans data/ (et dans les
    # sauvegardes du NAS, qui les répliquent chacune).
    copies = sorted(db_path.parent.glob("avant_restauration_*.db"), reverse=True)
    for vieille in copies[COPIES_DE_SECURITE_GARDEES:]:
        vieille.unlink(missing_ok=True)

    # Purge les connexions du pool puis migre la base restaurée si elle vient
    # d'une version antérieure de l'application.
    engine.dispose()
    ensure_schema(engine)

    from .journal import log_event
    from .seeding import ensure_profile

    # Session liée au moteur qu'on vient de migrer, et non à SessionLocal :
    # ce sont deux objets distincts, et n'importe quel écart entre les deux
    # ferait travailler la suite sur une autre base que celle restaurée.
    with Session(bind=engine) as session:
        # Une sauvegarde peut venir d'une base sans ligne de profil (table créée
        # mais jamais amorcée) : sans elle, toute l'application renverrait des 500.
        ensure_profile(session)
        log_event(session, "restauration",
                  f"Base restaurée depuis une sauvegarde ({offer_count} offres) — copie de sécurité : {safety_name}.")

    return {
        "restored": True,
        "offers": offer_count,
        "safety_copy": safety_name,
    }
