"""Appelle VRAIMENT istqb.org (règle du projet : pas de client HTTP bouchonné).
Source injoignable → test ignoré avec la raison ; source qui répond mal → échec."""
import urllib.error

import pytest

from qak import catalogue, extraction, recherche


def _joignable() -> str | None:
    """Même chemin que le vrai téléchargement (User-Agent de l'outil, domaine contrôlé).
    Réseau coupé ou accès refusé (403, pare-feu) → None impossible : on ignore avec la raison."""
    try:
        catalogue._ouvrir(catalogue.documents(["CTFL"])[0]["telechargement"], "HEAD", delai=20).close()
        return None
    except (urllib.error.URLError, OSError) as exc:
        return f"istqb.org injoignable : {exc}"


@pytest.fixture(scope="module")
def reseau():
    raison = _joignable()
    if raison:
        pytest.skip(raison)


def test_catalogue_toujours_servi_par_istqb(reseau):
    for code in ("CTFL", "CTAL-TM"):
        v = catalogue.verifier(catalogue.documents([code])[0])
        assert v["etat"] == "disponible", v
        assert v["fichier"].lower().endswith(".pdf")


def test_telechargement_officiel_extrait_et_indexe_le_ctfl(reseau):
    r = catalogue.telecharger(catalogue.documents(["CTFL"])[0])
    assert r["etat"] == "importe" and r["statut_extraction"] == "ok", r
    assert r["meta"]["code"] == "CTFL" and r["meta"]["langue"] == "en"
    res = recherche.chercher("partitions d'équivalence", n=3)["resultats"]
    assert any(x["section_num"].startswith("4.2") for x in res), res


def test_domaine_non_officiel_refuse():
    with pytest.raises(PermissionError):
        catalogue._ouvrir("https://exemple.org/syllabus.pdf")
