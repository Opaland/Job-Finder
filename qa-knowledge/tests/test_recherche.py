from qak import bibliotheque, recherche
from conftest import FIXTURES


def test_question_francaise_trouve_le_passage_anglais(bibliotheque_test):
    r = recherche.chercher("partitions d'équivalence")
    premier = r["resultats"][0]
    assert premier["section_num"] == "1.2" and premier["page"] == 5
    assert r["groupes"] == ["partition-equivalence"]


def test_couverture_des_notions_prime_sur_un_mot_isole(bibliotheque_test):
    r = recherche.chercher("priorisation des tests selon le niveau de risque")
    premier = r["resultats"][0]
    assert premier["section_num"] == "2.1" and not premier["partiel"]


def test_sommaires_et_index_exclus_par_defaut(bibliotheque_test):
    pages = {x["page"] for x in recherche.chercher("equivalence partitioning", n=20, par_doc=20)["resultats"]}
    assert 2 not in pages and 7 not in pages
    avec = {x["page"] for x in recherche.chercher("equivalence partitioning", n=20, par_doc=20, inclure_sommaires=True)["resultats"]}
    assert 7 in avec


def test_filtre_section_inclut_les_sous_sections(bibliotheque_test):
    r = recherche.chercher("partition", section="1.2")
    assert {x["section_num"] for x in r["resultats"]} <= {"1.2", "1.2.1"} and r["resultats"]
    assert not recherche.chercher("partition", section="2")["resultats"]


def test_version_remplacee_exclue_sauf_demande(bibliotheque_test):
    bibliotheque.importer(FIXTURES / "syllabus_v10.pdf")
    docs = {x["doc_id"] for x in recherche.chercher("test objectives", n=10)["resultats"]}
    assert docs == {"CTFL-10.0-en"}
    docs = {x["doc_id"] for x in recherche.chercher("test objectives", n=10, toutes_versions=True)["resultats"]}
    assert docs == {"CTFL-10.0-en", "CTFL-9.9-en"}


def test_lire_passage_avec_contexte_et_section(bibliotheque_test):
    pid = recherche.chercher("equivalence partitioning")["resultats"][0]["id"]
    autour = recherche.lire_passage(pid, contexte=1)
    assert len(autour) == 3 and any(p["id"] == pid for p in autour)
    section = recherche.lire_section(bibliotheque_test, "1.2")
    assert {p["section_num"] for p in section["passages"]} == {"1.2", "1.2.1"}
    assert recherche.lire_pages("CTFL", 5)["passages"]


def test_bibliotheque_vide_et_requete_vide(racine_isolee):
    assert "Bibliothèque vide" in recherche.chercher("risque")["avertissements"][0]
    assert recherche.chercher("le la les de")["resultats"] == []


def test_aucun_resultat_suggere_reformulation_ou_web(bibliotheque_test):
    r = recherche.chercher("blockchain quantique")
    assert not r["resultats"] and "Web" in r["avertissements"][0]


def test_filtre_par_theme(bibliotheque_test):
    r = recherche.chercher("tests", theme="rbt")
    assert r["resultats"] and all(x["section_num"] in ("2.1", "1.1") for x in r["resultats"])
