"""Verrou inter-processus du scan : l'interface et la tâche planifiée ne doivent
jamais scanner en même temps (deux index d'offres connues = doublons)."""
import pytest

from app.services.verrou import verrou_scan


def test_un_second_verrou_est_refuse(tmp_path):
    chemin = tmp_path / "scan.lock"
    with verrou_scan(chemin):
        with pytest.raises(RuntimeError, match="autre processus"):
            with verrou_scan(chemin):
                pass


def test_le_verrou_est_rendu_a_la_sortie(tmp_path):
    chemin = tmp_path / "scan.lock"
    with verrou_scan(chemin):
        pass
    with verrou_scan(chemin):
        pass  # repris sans erreur


def test_le_verrou_est_rendu_meme_en_cas_derreur(tmp_path):
    chemin = tmp_path / "scan.lock"
    with pytest.raises(ValueError):
        with verrou_scan(chemin):
            raise ValueError("scan en échec")
    with verrou_scan(chemin):
        pass
