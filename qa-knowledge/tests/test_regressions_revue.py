"""Non-régression des défauts trouvés par la revue du 2026-10-21 (un test par constat)."""
import json
import multiprocessing
import os

import pytest

from qak import bibliotheque, chemins, connaissances, extraction, recherche
from qak.connaissances import ErreurValidation
from conftest import FIXTURES

IDEE = {"titre": "Idée {n} sur un sujet distinct numéro {n}", "resume": "Résumé {n} zygomorphe{n}",
        "probleme": "Problème {n}", "principe": "Principe {n} quasar{n}", "theme_principal": "strategie"}


def _idee(n, **kw):
    return {**{k: v.format(n=n) for k, v in IDEE.items()}, **kw}


def _ajouter_en_parallele(args):
    racine, n = args
    os.environ["QAK_RACINE"] = racine
    return connaissances.ajouter(_idee(n), forcer=True, motif="test")["id"]


def test_1_ajouts_simultanes_identifiants_uniques(racine_isolee):
    with multiprocessing.get_context("spawn").Pool(6) as pool:
        ids = pool.map(_ajouter_en_parallele, [(str(racine_isolee), n) for n in range(6)])
    assert len(set(ids)) == 6
    assert len(connaissances.lister()) == 6


def test_2_identifiant_en_double_dans_le_jsonl_refuse_sans_perte():
    connaissances.ajouter(_idee(1))
    p = chemins.connaissances_jsonl()
    ligne = p.read_text(encoding="utf-8").splitlines()[0]
    autre = {**json.loads(ligne), "titre": "Autre côté du conflit"}
    p.write_text(ligne + "\n" + json.dumps(autre, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ErreurValidation, match="double"):
        connaissances.lister()
    assert len(p.read_text(encoding="utf-8").splitlines()) == 2  # rien n'a été réécrit


def test_3_identifiant_retire_jamais_reattribue():
    for n in range(3):
        connaissances.ajouter(_idee(n), forcer=True, motif="idées de test volontairement proches")
    connaissances.lier("QA-0001", "QA-0003", "complementaire")
    p = chemins.connaissances_jsonl()
    lignes = [l for l in p.read_text(encoding="utf-8").splitlines() if '"QA-0003"' not in l.split(",")[0]]
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    assert connaissances.ajouter(_idee(9), forcer=True, motif="t")["id"] == "QA-0004"


def test_4_filtre_theme_applique_avant_la_limite():
    for n in range(12):
        connaissances.ajouter({**_idee(n), "resume": f"tableau de bord numéro {n} quasar{n}"}, forcer=True, motif="t")
    cible = connaissances.ajouter({**_idee(99), "theme_principal": "rbt", "resume": "tableau de bord des risques"},
                                  forcer=True, motif="t")["id"]
    assert [r["id"] for r in connaissances.chercher("tableau de bord", n=3, theme="rbt")] == [cible]


def test_5_fichier_modifie_sur_place_garde_son_identite(racine_isolee):
    chemins.sources().mkdir(parents=True)
    f = chemins.sources() / "tm.md"
    f.write_text("# 1 Gestion\nVersion initiale du texte de gestion des tests.", encoding="utf-8")
    doc_id = bibliotheque.importer(f, {"code": "CTAL-TM", "version": "4.0"}, copier=False)["doc_id"]
    f.write_text("# 1 Gestion\nVersion corrigée du texte de gestion des tests.", encoding="utf-8")
    r = bibliotheque.actualiser()
    assert r["modifies"] and not r["importes"] and not r["absents"]
    docs = bibliotheque.inventaire()
    assert [(d["doc_id"], d["code"], d["version"]) for d in docs] == [(doc_id, "CTAL-TM", "4.0")]
    assert recherche.chercher("corrigée")["resultats"]


def test_6_numero_de_version_prime_sur_une_date_isolee():
    a = {"version": "3.0", "date_publication": "2012-10-19"}
    b = {"version": "4.0", "date_publication": None}
    assert bibliotheque._comparer_versions(b, a) == 1
    # « 2019 » est une année, pas un numéro : la date tranche (CTAL-TA FR 2019 vs v4.0 de 2025).
    assert bibliotheque._comparer_versions({"version": "4.0", "date_publication": "2025-05-01"},
                                           {"version": "2019", "date_publication": "2019-12-19"}) == 1


def test_7_references_page_exacte_section_et_source_absente(bibliotheque_test):
    extrait_p5 = "Equivalence partitioning divides data into partitions"
    with pytest.raises(ErreurValidation, match="n'apparaît pas"):  # extrait de la p. 5 cité en p. 4
        connaissances.valider({**_idee(1), "references": [{"type": "istqb", "doc_id": "CTFL", "pages": "4",
                                                           "extrait": extrait_p5}]})
    connaissances.valider({**_idee(1), "references": [{"type": "istqb", "doc_id": "CTFL", "section": "1.2",
                                                       "extrait": extrait_p5}]})
    with pytest.raises(ErreurValidation, match="Section 9.9 absente"):
        connaissances.valider({**_idee(1), "references": [{"type": "istqb", "doc_id": "CTFL", "section": "9.9"}]})
    connaissances.ajouter({**_idee(1), "references": [{"type": "istqb", "doc_id": "CTFL", "pages": "5"}]})
    (chemins.sources() / "syllabus_v9.pdf").unlink()
    bibliotheque.actualiser()
    assert "absent" in connaissances.verifier_references()[0]["problemes"][0]
    assert connaissances._pages("4, 6") == {4, 6} and connaissances._pages("31-33") == {31, 32, 33}


def test_8_doc_remplace_demande_explicitement_reste_cherchable(bibliotheque_test):
    bibliotheque.importer(FIXTURES / "syllabus_v10.pdf")
    r = recherche.chercher("equivalence partitioning", docs=["CTFL-9.9-en"])
    assert r["resultats"] and {x["doc_id"] for x in r["resultats"]} == {"CTFL-9.9-en"}


def test_9_sigles_courts_gardes_mots_courts_signales(bibliotheque_test):
    assert "sql" in recherche.chercher("injection SQL")["groupes"]
    r = recherche.chercher("risk sql")
    assert any("ignorés : sql" in w for w in r["avertissements"])


def test_10_titre_de_signet_coupe_sur_deux_lignes():
    lignes = ["fin du texte de la section 4.1.", "4.2 Black-box Test", "Techniques Used in Practice", "Texte."]
    assert extraction._ligne_du_titre(lignes, "4.2", "Black-box Test Techniques Used in Practice") == 1
    assert extraction._ligne_du_titre(["texte", "4.3 Titre très différent"], "4.3", "Autre libellé") == 1
