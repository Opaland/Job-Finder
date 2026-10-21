import json
import re
from urllib.parse import urlparse

from qak import bibliotheque, chemins, textes


def test_thesaurus_un_terme_un_seul_concept():
    vus = {}
    for cid, termes in textes.thesaurus():
        for t in termes:
            n = textes.normaliser(t)
            assert n not in vus, f"« {t} » dans {vus.get(n)} et {cid}"
            vus[n] = cid


def test_catalogue_officiel_coherent():
    cat = bibliotheque.catalogue()
    codes = [d["code"] for d in cat["documents"]]
    assert len(codes) == len(set(codes)) >= 25
    for d in cat["documents"]:
        assert urlparse(d["telechargement"]).hostname == "istqb.org"
        assert urlparse(d["page_officielle"]).hostname == "istqb.org"
        assert d["niveau"] in ("fondation", "avance", "expert", "specialiste")
        for m in d["motifs"]:
            re.compile(m)
    assert cat["domaines_autorises"] == ["istqb.org"]


def test_jeu_d_evaluation_bien_forme():
    cas = json.loads((chemins.CODE / "eval" / "requetes.json").read_text(encoding="utf-8"))["cas"]
    codes = {d["code"] for d in bibliotheque.catalogue()["documents"]}
    assert len(cas) >= 40 and sum(bool(c.get("controle")) for c in cas) >= 10
    assert all(a["code"] in codes for c in cas for a in c["attendus"])
