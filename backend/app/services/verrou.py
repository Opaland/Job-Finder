"""Verrou inter-processus : un seul scan à la fois sur la machine.

L'interface (uvicorn) et la tâche planifiée (`scan.bat` → `python -m app.cli scan`)
sont deux processus distincts : le verrou mémoire de `scan.py` ne les voit pas
l'un l'autre. Un fichier verrouillé par le système dans `data/` les met d'accord,
sans quoi deux scans simultanés créeraient des doublons (chacun construit son
index d'offres connues avant que l'autre n'insère les siennes).
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path

from ..config import DATA_DIR

try:                                  # POSIX (Linux, Raspberry Pi, NAS)
    import fcntl
except ImportError:                   # pragma: no cover — Windows
    fcntl = None
try:                                  # Windows (poste de Cédric)
    import msvcrt
except ImportError:                   # pragma: no cover — POSIX
    msvcrt = None

logger = logging.getLogger("jobfinder.verrou")

VERROU_SCAN = DATA_DIR / "scan.lock"

MESSAGE_SCAN_AILLEURS = (
    "Un scan est déjà en cours dans un autre processus (tâche planifiée ou autre "
    "fenêtre de l'application) — attends qu'il se termine avant d'en lancer un."
)


def _essayer_de_verrouiller(descripteur: int) -> bool:
    """Verrou exclusif non bloquant. True si obtenu, False s'il est déjà pris."""
    if fcntl is not None:
        try:
            fcntl.flock(descripteur, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    if msvcrt is not None:  # pragma: no cover — testé sous Windows uniquement
        try:
            msvcrt.locking(descripteur, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    # Plateforme sans verrou de fichier : on ne bloque pas l'utilisateur.
    logger.warning("Verrous de fichier indisponibles : scans concurrents non détectés.")
    return True


def _deverrouiller(descripteur: int) -> None:
    if fcntl is not None:
        fcntl.flock(descripteur, fcntl.LOCK_UN)
    elif msvcrt is not None:  # pragma: no cover — testé sous Windows uniquement
        os.lseek(descripteur, 0, 0)
        msvcrt.locking(descripteur, msvcrt.LK_UNLCK, 1)


@contextmanager
def verrou_scan(chemin: Path = VERROU_SCAN):
    """Prend le verrou de scan, ou lève `RuntimeError` s'il est tenu ailleurs.

    Le fichier n'est jamais supprimé : c'est le verrou posé dessus qui compte,
    et un processus tué le relâche automatiquement (fermeture du descripteur).
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fichier = open(chemin, "a+b")
    try:
        if not _essayer_de_verrouiller(fichier.fileno()):
            raise RuntimeError(MESSAGE_SCAN_AILLEURS)
        try:
            yield
        finally:
            _deverrouiller(fichier.fileno())
    finally:
        fichier.close()


def verrou_disponible(chemin: Path = VERROU_SCAN) -> bool:
    """True si un scan peut démarrer maintenant (aucun autre processus n'en fait).

    Sert à répondre tout de suite à l'utilisateur ; le verrou définitif est
    repris par `run_scan`.
    """
    try:
        with verrou_scan(chemin):
            return True
    except RuntimeError:
        return False
