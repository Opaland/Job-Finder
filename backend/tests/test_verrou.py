"""Verrou inter-processus du scan : l'interface et la tâche planifiée ne doivent
jamais scanner en même temps (deux index d'offres connues = doublons)."""
import os

import pytest

import app.services.verrou as verrou_module
from app.services.verrou import verrou_disponible, verrou_scan


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


# --- Sprint 61 : trous relevés par mutation testing ---------------------------

def test_verrou_disponible_vrai_si_libre(tmp_path):
    assert verrou_disponible(tmp_path / "scan.lock") is True


def test_verrou_disponible_faux_si_deja_pris(tmp_path):
    chemin = tmp_path / "scan.lock"
    with verrou_scan(chemin):
        assert verrou_disponible(chemin) is False


class _FauxMsvcrt:
    """Simule le module `msvcrt` (Windows) pour l'éprouver sous Linux."""
    LK_NBLCK = 1
    LK_UNLCK = 0

    def __init__(self, leve=False):
        self.appels = []
        self.leve = leve

    def locking(self, descripteur, mode, nbytes):
        self.appels.append((descripteur, mode, nbytes))
        if self.leve:
            raise OSError("verrou déjà pris")


def test_essayer_de_verrouiller_utilise_msvcrt_si_fcntl_absent(tmp_path, monkeypatch):
    """Poste Windows de Cédric (pas de fcntl) : le verrou doit passer par msvcrt,
    pas silencieusement réussir sans rien verrouiller."""
    faux = _FauxMsvcrt()
    monkeypatch.setattr(verrou_module, "fcntl", None)
    monkeypatch.setattr(verrou_module, "msvcrt", faux)
    fichier = open(tmp_path / "scan.lock", "a+b")
    try:
        assert verrou_module._essayer_de_verrouiller(fichier.fileno()) is True
        assert faux.appels == [(fichier.fileno(), _FauxMsvcrt.LK_NBLCK, 1)]
    finally:
        fichier.close()


def test_essayer_de_verrouiller_msvcrt_refuse_si_deja_pris(tmp_path, monkeypatch):
    monkeypatch.setattr(verrou_module, "fcntl", None)
    monkeypatch.setattr(verrou_module, "msvcrt", _FauxMsvcrt(leve=True))
    fichier = open(tmp_path / "scan.lock", "a+b")
    try:
        assert verrou_module._essayer_de_verrouiller(fichier.fileno()) is False
    finally:
        fichier.close()


def test_essayer_de_verrouiller_sans_aucun_mecanisme_autorise_quand_meme(tmp_path, monkeypatch, caplog):
    """Plateforme sans fcntl ni msvcrt : ne doit jamais bloquer l'utilisateur —
    juste prévenir que les scans concurrents ne sont plus détectés."""
    monkeypatch.setattr(verrou_module, "fcntl", None)
    monkeypatch.setattr(verrou_module, "msvcrt", None)
    fichier = open(tmp_path / "scan.lock", "a+b")
    try:
        with caplog.at_level("WARNING"):
            assert verrou_module._essayer_de_verrouiller(fichier.fileno()) is True
        assert "indisponibles" in caplog.text
    finally:
        fichier.close()


def test_verrou_scan_cree_le_dossier_parent_manquant(tmp_path):
    """`mkdir(parents=True, ...)` : un seul niveau manquant se crée même avec
    `parents=False` (son propre parent existe déjà) — sans vraie distinction.
    Deux niveaux manquants d'un coup exigent `parents=True` pour de vrai."""
    chemin = tmp_path / "a" / "b" / "scan.lock"
    assert not chemin.parent.exists()
    assert not chemin.parent.parent.exists()
    with verrou_scan(chemin):
        pass
    assert chemin.parent.exists()


def test_deverrouiller_utilise_msvcrt_si_fcntl_absent(tmp_path, monkeypatch):
    faux = _FauxMsvcrt()
    monkeypatch.setattr(verrou_module, "fcntl", None)
    monkeypatch.setattr(verrou_module, "msvcrt", faux)
    fichier = open(tmp_path / "scan.lock", "a+b")
    try:
        fichier.write(b"x" * 10)
        fichier.flush()
        os.lseek(fichier.fileno(), 5, 0)  # position non nulle avant déverrouillage
        verrou_module._deverrouiller(fichier.fileno())
        assert faux.appels == [(fichier.fileno(), _FauxMsvcrt.LK_UNLCK, 1)]
        # `os.lseek(descripteur, 0, 0)` : msvcrt.locking() vise l'octet verrouillé
        # au début du fichier, pas la position où l'écriture s'est arrêtée.
        assert os.lseek(fichier.fileno(), 0, 1) == 0
    finally:
        fichier.close()
