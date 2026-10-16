"""Helpers partagés de services/textutils.py testés directement."""
from app.services.textutils import teletravail_complet


def test_teletravail_total_est_complet():
    assert teletravail_complet("Télétravail total") is True
    assert teletravail_complet("100% remote") is True
    assert teletravail_complet("Full remote, CDI") is True


def test_teletravail_partiel_n_est_pas_complet():
    """Cœur du bug corrigé (issues #9/#35) : 13 pts/15 sont réservés au full
    remote (scoring.py) — un jour par semaine ne doit jamais les déclencher."""
    for mention in ("télétravail partiel", "télétravail hybride", "télétravail 2 jours",
                    "télétravail ponctuel", "télétravail occasionnel"):
        assert teletravail_complet(mention) is False, mention


def test_sans_mention_de_teletravail():
    assert teletravail_complet("CDI, Lyon, sur site") is False


def test_plusieurs_segments_le_bon_segment_tranche():
    """Chaque argument est un segment indépendant — un segment « partiel »
    qualifie SA mention, pas celle d'un autre segment resté muet."""
    assert teletravail_complet("Lyon", "CDI", "Télétravail partiel") is False
    assert teletravail_complet("Lyon", "CDI", "Télétravail total") is True
