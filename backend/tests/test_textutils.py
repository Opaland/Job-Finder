"""Helpers partagés de services/textutils.py testés directement."""
from datetime import datetime

from app.services.textutils import contains_word, naif, teletravail_complet, titles_similar


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


def test_naif_laisse_une_date_deja_naive_inchangee():
    """Sans tzinfo, naif() doit renvoyer la date telle quelle — pas la faire
    passer par une conversion de fuseau qui n'a pas de sens sans décalage."""
    deja_naive = datetime(2026, 10, 17, 9, 30)
    assert naif(deja_naive) == deja_naive
    assert naif(deja_naive).tzinfo is None


def test_contains_word_needle_vide_ne_matche_jamais():
    assert contains_word("test manager senior", "") is False
    assert contains_word("test manager senior", "   ") is False


def test_titles_similar_faux_si_un_titre_est_vide():
    assert titles_similar("", "Test Manager") is False
    assert titles_similar("Test Manager", "") is False


def test_titles_similar_a_sa_frontiere_exacte():
    """Seuil 0.88 (dédoublonnage inter-sources, scan.py) jamais testé pile à
    sa frontière : le seul cas existant avant cette issue avait un ratio de
    0.94, loin du seuil. Paire construite pour straddler 0.88 avec des mots
    distincts (pas de court-circuit "mêmes mots, ordre différent")."""
    base = "Test Manager Qualite Logicielle"
    assert titles_similar(base, base + " alphabb") is True     # ratio ≈ 0.886, au-dessus
    assert titles_similar(base, base + " alphabbb") is False   # ratio ≈ 0.873, en-dessous


def test_titles_similar_pile_au_seuil_est_considere_similaire(monkeypatch):
    """0.88 pile doit compter comme similaire (`>=`, pas `>`) — construire une
    paire de titres réels à ce ratio exact est fragile, donc le ratio est
    simulé directement pour isoler la frontière elle-même."""
    import difflib

    monkeypatch.setattr(difflib.SequenceMatcher, "ratio", lambda self: 0.88)
    assert titles_similar("Test Manager", "Responsable Qualite") is True
