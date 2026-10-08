"""Tests de app.cli : la tâche planifiée doit signaler ses pannes, pas juste réussir en silence.

Avant correction : un échec d'envoi d'email ou un verrou de scan occupé (qu'il
s'agisse d'un chevauchement normal ou d'un verrou resté bloqué) sortaient tous
les deux en code 0 — invisibles pour le Planificateur de tâches Windows.
"""
from datetime import timedelta

import pytest

from app import cli
from app.models import ScanRun, local_now


def _scan_termine(db, il_y_a: timedelta) -> ScanRun:
    run = ScanRun(status="termine", finished_at=local_now() - il_y_a)
    db.add(run)
    db.commit()
    return run


def test_verrou_occupe_apres_un_scan_recent_est_juste_ignore(db, capsys):
    """Chevauchement normal (scan réussi il y a 2h) : pas une alerte."""
    _scan_termine(db, timedelta(hours=2))
    cli._signaler_scan_ignore(db, RuntimeError("Un scan est déjà en cours ailleurs"))
    assert "ignoré" in capsys.readouterr().out


def test_verrou_occupe_sans_scan_reussi_depuis_longtemps_est_une_erreur(db, capsys):
    """Aucun scan réussi depuis 5 jours : le verrou est probablement resté bloqué."""
    _scan_termine(db, timedelta(days=5))
    with pytest.raises(SystemExit) as exc:
        cli._signaler_scan_ignore(db, RuntimeError("Un scan est déjà en cours ailleurs"))
    assert exc.value.code == 1
    assert "bloqué" in capsys.readouterr().err


def test_verrou_occupe_sans_aucun_scan_jamais_reussi_est_une_erreur(db, capsys):
    """Aucune ligne ScanRun « terminé » du tout : même traitement, pas de crash sur None."""
    with pytest.raises(SystemExit) as exc:
        cli._signaler_scan_ignore(db, RuntimeError("Un scan est déjà en cours ailleurs"))
    assert exc.value.code == 1
    assert "jamais réussi" in capsys.readouterr().err


def test_email_non_envoye_avec_smtp_configure_echoue(db, monkeypatch, capsys):
    """Le scan réussit mais l'email échoue, SMTP pourtant configuré : code ≠ 0."""
    run = ScanRun(status="termine", new_count=3, error_count=0)
    digest = type("DigestFactice", (), {"date": "2026-10-08"})()

    monkeypatch.setattr(cli, "ensure_schema_avec_verrou", lambda engine: None)
    monkeypatch.setattr(cli, "run_full_scan", lambda db, trigger, send_email: (run, digest, False))
    monkeypatch.setattr(cli, "smtp_configured", lambda: True)
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli.sys, "argv", ["app.cli", "scan"])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert "email" in capsys.readouterr().err.lower()


def test_email_non_envoye_sans_smtp_configure_est_normal(db, monkeypatch, capsys):
    """SMTP non configuré (cas courant hors poste de Cédric) : pas d'échec pour autant."""
    run = ScanRun(status="termine", new_count=3, error_count=0)
    digest = type("DigestFactice", (), {"date": "2026-10-08"})()

    monkeypatch.setattr(cli, "ensure_schema_avec_verrou", lambda engine: None)
    monkeypatch.setattr(cli, "run_full_scan", lambda db, trigger, send_email: (run, digest, False))
    monkeypatch.setattr(cli, "smtp_configured", lambda: False)
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli.sys, "argv", ["app.cli", "scan"])

    cli.main()  # ne lève pas
    assert "email envoyé : False" in capsys.readouterr().out
