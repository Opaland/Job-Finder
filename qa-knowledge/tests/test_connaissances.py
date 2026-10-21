import json

import pytest

from qak import chemins, connaissances, journal, taxonomie
from qak.connaissances import ErreurValidation

IDEE = {
    "titre": "Matrice probabilité × impact pour prioriser les tests",
    "resume": "Noter probabilité et impact de chaque risque produit pour ordonner les tests.",
    "probleme": "Effort de test réparti uniformément alors que les risques sont inégaux.",
    "principe": "Niveau de risque = probabilité × impact ; profondeur et ordre de test en découlent.",
    "theme_principal": "rbt",
}


def test_ajout_minimal_valeurs_par_defaut_et_miroir_jsonl():
    r = connaissances.ajouter(dict(IDEE))
    assert r["etat"] == "cree" and r["id"] == "QA-0001"
    i = connaissances.voir("QA-0001")
    assert (i["statut"], i["maturite"]) == ("a_explorer", "hypothese")
    lignes = chemins.connaissances_jsonl().read_text(encoding="utf-8").splitlines()
    assert json.loads(lignes[0])["titre"] == IDEE["titre"]
    assert journal.lire("QA-0001")[0]["action"] == "idee_creee"


def test_champs_obligatoires_et_valeurs_controlees():
    with pytest.raises(ErreurValidation, match="principe"):
        connaissances.ajouter({k: v for k, v in IDEE.items() if k != "principe"})
    with pytest.raises(ErreurValidation, match="statut invalide"):
        connaissances.ajouter({**IDEE, "statut": "termine"})
    with pytest.raises(ErreurValidation, match="validée"):
        connaissances.ajouter({**IDEE, "statut": "validee"})
    with pytest.raises(KeyError, match="Thème inconnu"):
        connaissances.ajouter({**IDEE, "theme_principal": "inexistant"})
    with pytest.raises(ErreurValidation, match="URL"):
        connaissances.ajouter({**IDEE, "references": [{"type": "web", "titre": "sans lien"}]})


def test_doublon_reformule_bloque_puis_force_avec_motif():
    connaissances.ajouter(dict(IDEE))
    reformule = {**IDEE, "titre": "Prioriser les tests avec une matrice impact / probabilité",
                 "resume": "Ordonner les tests selon probabilité et impact des risques produit."}
    r = connaissances.ajouter(reformule)
    assert r["etat"] == "refuse" and r["doublons"][0]["id"] == "QA-0001"
    with pytest.raises(ErreurValidation, match="motif"):
        connaissances.ajouter(reformule, forcer=True)
    assert connaissances.ajouter(reformule, forcer=True, motif="variante orientée agile")["etat"] == "cree"


def test_doublon_detecte_entre_francais_et_anglais():
    connaissances.ajouter({**IDEE, "titre": "Partitions d'équivalence pour réduire le nombre de cas de test",
                           "theme_principal": "boite-noire"})
    sim = connaissances.doublons({"titre": "Equivalence partitioning", "resume": "reduce the number of test cases",
                                  "principe": "", "probleme": ""})
    assert sim and sim[0]["id"] == "QA-0001"


def test_idee_differente_non_signalee():
    connaissances.ajouter(dict(IDEE))
    autre = {**IDEE, "titre": "Charte de session exploratoire", "resume": "Cadrer une session exploratoire de 90 min.",
             "probleme": "Tests exploratoires non traçables.", "principe": "Charte, timebox, debriefing.",
             "theme_principal": "exploratoire"}
    assert connaissances.doublons(autre) == []


def test_modifier_ajoute_les_references_sans_perdre_les_anciennes():
    connaissances.ajouter({**IDEE, "references": [{"type": "web", "url": "https://exemple.org/a", "titre": "A"}]})
    connaissances.modifier("QA-0001", {"references": [{"type": "web", "url": "https://exemple.org/b", "titre": "B"}],
                                       "themes_secondaires": ["priorisation"]})
    i = connaissances.voir("QA-0001")
    assert [r["url"] for r in i["references"]] == ["https://exemple.org/a", "https://exemple.org/b"]
    assert all(r.get("consulte_le") for r in i["references"])
    assert i["themes_secondaires"] == ["priorisation"]
    assert connaissances.modifier("QA-0001", {"titre": IDEE["titre"]})["etat"] == "inchange"
    with pytest.raises(ErreurValidation, match="idee statut"):
        connaissances.modifier("QA-0001", {"statut": "validee"})


def test_regles_de_statut():
    connaissances.ajouter(dict(IDEE))
    with pytest.raises(ErreurValidation, match="motif"):
        connaissances.changer_statut("QA-0001", "validee", None)
    with pytest.raises(ErreurValidation, match="retour"):
        connaissances.changer_statut("QA-0001", "experimentee", "essai")
    connaissances.ajouter_retour("QA-0001", "Release 3.2", "2 défauts critiques trouvés plus tôt")
    assert connaissances.changer_statut("QA-0001", "experimentee", "appliqué en 3.2")["apres"] == "experimentee"
    assert [e["action"] for e in journal.lire("QA-0001")] == ["idee_creee", "retour_ajoute", "statut_change"]


def test_relations_dans_les_deux_sens():
    connaissances.ajouter(dict(IDEE))
    connaissances.ajouter({**IDEE, "titre": "Charte exploratoire", "resume": "Session de 90 min cadrée.",
                           "probleme": "Exploratoire non tracé.", "principe": "Charte et debriefing.",
                           "theme_principal": "exploratoire"})
    connaissances.lier("QA-0002", "QA-0001", "complementaire", "les risques orientent les chartes")
    assert connaissances.voir("QA-0002")["relations"][0]["cible"] == "QA-0001"
    assert connaissances.voir("QA-0001")["relations_entrantes"][0]["source"] == "QA-0002"
    with pytest.raises(ErreurValidation):
        connaissances.lier("QA-0001", "QA-0001", "variante")
    with pytest.raises(KeyError):
        connaissances.lier("QA-0001", "QA-9999", "variante")


def test_base_reconstruite_depuis_le_jsonl_apres_git_pull():
    connaissances.ajouter(dict(IDEE))
    # Simule un `git pull` qui apporte une idée saisie sur un autre poste.
    p = chemins.connaissances_jsonl()
    autre = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    autre.update(id="QA-0002", titre="Idée venue d'un autre poste")
    p.write_text(p.read_text(encoding="utf-8") + json.dumps(autre, ensure_ascii=False) + "\n", encoding="utf-8")
    assert [i["id"] for i in connaissances.lister()] == ["QA-0001", "QA-0002"]
    # Base supprimée : reconstruite à l'identique depuis le miroir versionné.
    chemins.base_db().unlink()
    assert connaissances.voir("QA-0002")["titre"] == "Idée venue d'un autre poste"


def test_recherche_et_liste_par_theme_avec_sous_themes():
    connaissances.ajouter(dict(IDEE))
    assert connaissances.chercher("risk prioritization")[0]["id"] == "QA-0001"  # requête anglaise, idée française
    assert [i["id"] for i in connaissances.lister(theme="test-management")] == ["QA-0001"]  # rbt ⊂ test-management
    assert connaissances.lister(theme="exploratoire") == []


def test_theme_obsolete_resolu_vers_son_remplacant():
    taxonomie.rendre_obsolete("priorisation", "rbt", "fusion des thèmes")
    r = connaissances.ajouter({**IDEE, "theme_principal": "priorisation"})
    assert any("obsolète" in w for w in r["avertissements"])
    assert connaissances.voir(r["id"])["theme_principal"] == "rbt"


def test_references_istqb_verifiees_contre_la_bibliotheque(bibliotheque_test):
    ok = {**IDEE, "references": [{"type": "istqb", "doc_id": "CTFL", "pages": "6",
                                  "extrait": "Risk level is determined by risk likelihood and risk impact"}]}
    r = connaissances.ajouter(ok)
    ref = connaissances.voir(r["id"])["references"][0]
    assert (ref["doc_id"], ref["version"]) == (bibliotheque_test, "9.9")  # complété depuis l'index
    with pytest.raises(ErreurValidation, match="inexistante"):
        connaissances.valider({**IDEE, "references": [{"type": "istqb", "doc_id": "CTFL", "pages": "40"}]})
    with pytest.raises(ErreurValidation, match="n'apparaît pas"):
        connaissances.valider({**IDEE, "references": [{"type": "istqb", "doc_id": "CTFL", "pages": "6",
                                                       "extrait": "mutation testing guarantees complete coverage"}]})
    with pytest.raises(ErreurValidation, match="ni section"):
        connaissances.valider({**IDEE, "references": [{"type": "istqb", "doc_id": "CTFL"}]})
    _, avert = connaissances.valider({**IDEE, "references": [{"type": "istqb", "doc_id": "CTAL-TM", "pages": "3"}]})
    assert "absent de la bibliothèque" in avert[0]
    assert connaissances.verifier_references()[0]["problemes"] == []


def test_couverture_signale_les_themes_vides():
    connaissances.ajouter(dict(IDEE))
    rows = {r["code"]: r for r in connaissances.couverture()}
    assert rows["rbt"]["idees"] == 1 and rows["rbt"]["etat"] == "pauvre"
    assert rows["exploratoire"]["etat"] == "vide" and rows["exploratoire"]["passages"] is None
