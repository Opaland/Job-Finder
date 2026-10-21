import json

import pytest

from qak import chemins, journal, taxonomie

# Thèmes exigés par le cahier des charges (libellés de la taxonomie initiale).
THEMES_DEMANDES = ["Stratégie et gouvernance QA", "Test management", "Risk-Based Testing",
                   "Analyse et conception des tests", "Tests fonctionnels", "Tests non fonctionnels",
                   "Automatisation des tests", "Test d'API et de services", "Tests de performance",
                   "Tests de sécurité", "Tests exploratoires", "Shift-left et shift-right",
                   "CI/CD et qualité des pipelines", "Gestion des anomalies", "Exigences et critères d'acceptation",
                   "Métriques et reporting", "Maturité et amélioration continue", "TMMi et référentiels qualité",
                   "IA et ingénierie des tests", "Qualité logicielle réglementée",
                   "Outils, méthodes et organisation des équipes"]


def test_taxonomie_initiale_coherente_et_complete():
    themes = taxonomie.themes()
    codes = [t["code"] for t in themes]
    assert len(codes) == len(set(codes))
    assert all(t["parent"] in codes for t in themes if t["parent"])
    assert all(t["mots_cles"] for t in themes)
    libelles = {t["libelle"] for t in themes}
    assert not [l for l in THEMES_DEMANDES if l not in libelles]
    assert taxonomie.chemin("rbt") == "Test management › Risk-Based Testing"


def test_sous_theme_redondant_refuse_puis_distinct_accepte():
    with pytest.raises(ValueError, match="redondant"):
        taxonomie.ajouter("risques-produit", "Analyse des risques produit", "rbt", ["product risk"], "essai")
    t = taxonomie.ajouter("contract-testing", "Contract testing consommateur", "api",
                          ["consumer-driven contract", "pact"], "distinct du test d'API générique", forcer=True)
    assert taxonomie.chemin(t["code"]).endswith("Contract testing consommateur")
    # La taxonomie modifiée est écrite dans la racine de données, et journalisée.
    data = json.loads((chemins.racine() / "referentiel" / "taxonomie.json").read_text(encoding="utf-8"))
    assert data["version"] == 2 and journal.lire("contract-testing")[0]["motif"]


def test_ajout_exige_motif_code_valide_et_parent_existant():
    with pytest.raises(ValueError, match="motif"):
        taxonomie.ajouter("gouvernance-donnees", "Gouvernance des données de test", None, [], "")
    with pytest.raises(ValueError, match="invalide"):
        taxonomie.ajouter("Mauvais Code", "x", None, [], "m")
    with pytest.raises(KeyError):
        taxonomie.ajouter("xyz-abc", "Sujet inédit zzz", "parent-inexistant", [], "m")


def test_theme_obsolete_conserve_l_historique():
    taxonomie.rendre_obsolete("priorisation", "rbt", "fusion")
    t = taxonomie.theme("priorisation")
    assert t["statut"] == "obsolete" and t["remplace_par"] == "rbt"
    assert taxonomie.resoudre("priorisation") == "rbt"
    assert "priorisation" in [x["code"] for x in taxonomie.themes()]


def test_proposer_un_theme():
    codes = [c for _, c in taxonomie.proposer("tests Playwright instables et coûteux à maintenir")]
    assert codes[0] == "maintenance-automatisation"
