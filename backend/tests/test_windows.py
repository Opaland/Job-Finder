"""Invariants de la chaîne Windows — elle n'est jamais exécutée en CI (Linux).

Faute de pouvoir la lancer, on vérifie ce qui peut l'être statiquement : les
défauts trouvés ici sont ceux qui l'ont réellement cassée.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent.parent
BATS = sorted(RACINE.glob("*.bat")) + sorted((RACINE / "scripts").glob("*.bat"))


def test_il_y_a_bien_des_bat_a_verifier():
    """Garde-fou du garde-fou : si les .bat déménagent, les tests suivants
    passeraient à vide sans rien vérifier."""
    noms = {f.name for f in BATS}
    assert {"start.bat", "scan.bat", "installer-tache-quotidienne.bat", "verif.bat"} <= noms


@pytest.mark.parametrize("fichier", BATS, ids=lambda f: f.name)
def test_les_messages_affiches_restent_en_ascii(fichier):
    """cmd.exe lit un .bat dans la page de codes du poste (850/1252), pas en
    UTF-8 : un accent dans un `echo` s'affiche en charabia chez l'utilisateur."""
    fautifs = [
        f"{numero}: {ligne.strip()}"
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1)
        if re.match(r"\s*echo\b", ligne, re.I) and not ligne.isascii()
    ]
    assert not fautifs, f"accents dans un echo de {fichier.name} : {fautifs}"


@pytest.mark.parametrize("fichier", BATS, ids=lambda f: f.name)
def test_aucun_chemin_python_relatif_avec_pushd(fichier):
    """Régression : verif.bat définissait PY=backend\\venv\\... puis faisait
    « pushd backend » — le chemin pointait alors vers backend\\backend\\venv et
    pytest ne démarrait jamais."""
    texte = fichier.read_text(encoding="utf-8")
    if "pushd" not in texte.lower():
        pytest.skip("pas de pushd dans ce fichier")
    for ligne in texte.splitlines():
        trouve = re.match(r'\s*set\s+"PY=(?!%)([^"]*venv[^"]*)"', ligne, re.I)
        assert not trouve, f"chemin Python relatif dans {fichier.name} : {ligne.strip()}"


def test_gitattributes_impose_les_bonnes_fins_de_ligne():
    """Un .bat en LF casse cmd.exe (labels, blocs) ; un .sh en CRLF casse bash
    (« \\r : commande introuvable ») — or le hook Git du projet est un .sh."""
    regles = (RACINE / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.bat\s+text\s+eol=crlf", regles, re.M)
    assert re.search(r"^\*\.sh\s+text\s+eol=lf", regles, re.M)


def test_la_tache_planifiee_produit_un_xml_valide():
    """Le modèle est complété par installer-tache-quotidienne.bat : on rejoue la
    substitution et on vérifie que le Planificateur recevrait du XML valide."""
    modele = (RACINE / "tache-quotidienne.xml").read_text(encoding="utf-8")
    assert "__CHEMIN_SCAN__" in modele and "__DOSSIER__" in modele

    rendu = (modele.replace("__CHEMIN_SCAN__", r"C:\Users\Cedric\Job-Finder\scan.bat")
                   .replace("__DOSSIER__", r"C:\Users\Cedric\Job-Finder"))
    assert "__" not in rendu, "un marqueur de substitution est resté dans le XML"

    espace = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
    racine = ET.fromstring(rendu)
    commande = racine.find(f"{espace}Actions/{espace}Exec/{espace}Command")
    assert commande is not None and commande.text.endswith("scan.bat")
    # Le réveil du PC en veille est la raison d'être de cette tâche.
    assert racine.find(f"{espace}Settings/{espace}WakeToRun").text == "true"
    # Deux scans en parallèle sont déjà bloqués par le verrou, mais autant que
    # le Planificateur ne les lance pas non plus.
    assert racine.find(f"{espace}Settings/{espace}MultipleInstancesPolicy").text == "IgnoreNew"


def test_le_scan_planifie_laisse_une_trace():
    """Une tâche qui échoue à 07h25 sans journal ne laisse qu'un code de sortie
    dans le Planificateur : impossible à diagnostiquer."""
    texte = (RACINE / "scan.bat").read_text(encoding="utf-8")
    assert "scan-quotidien.log" in texte
    assert ">> " in texte and "2>&1" in texte
    assert "exit /b %CODE%" in texte, "le code de sortie doit remonter au Planificateur"
