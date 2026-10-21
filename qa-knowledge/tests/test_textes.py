from qak import textes


def test_normaliser_retire_accents_apostrophes_et_ponctuation():
    assert textes.normaliser("Partitions d’Équivalence !") == "partitions d equivalence"


def test_concepts_reconnus_en_francais_et_au_pluriel():
    concepts, reste = textes.reperer_concepts("Les partitions d'équivalence et les valeurs limites")
    ids = [c for c, _ in concepts]
    assert ids == ["partition-equivalence", "valeurs-limites"]
    assert "partitions" not in reste and "equivalence" not in reste


def test_expression_longue_prioritaire_sur_terme_court():
    concepts, _ = textes.reperer_concepts("analyse statique du code")
    assert [c for c, _ in concepts] == ["analyse-statique"]


def test_signature_identique_en_francais_et_en_anglais():
    fr = textes.signature("Partitions d'équivalence")
    en = textes.signature("Equivalence partitioning")
    assert fr == en == {"#partition-equivalence"}


def test_mots_vides_et_generiques_ne_pesent_pas():
    _, reste = textes.reperer_concepts("Quelles techniques ISTQB pour la stratégie de test ?")
    assert "quelles" not in reste and "pour" not in reste


def test_jaccard_et_recouvrement():
    assert textes.jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert textes.recouvrement({"a"}, {"a", "b", "c"}) == 1.0
    assert textes.jaccard(set(), {"a"}) == 0.0
