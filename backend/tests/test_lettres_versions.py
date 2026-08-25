"""Sprint 24 : historique des versions de lettre de motivation."""
from app.models import Offer
from app.routers.offers import MAX_VERSIONS_LETTRE


def _offre(db, lettre=""):
    offer = Offer(fingerprint="fp-lettre", source="manuelle", source_id="l1",
                  title="Test Manager", company="ACME", final_score=88.0, cover_letter=lettre)
    db.add(offer)
    db.commit()
    return offer


def test_edition_archive_la_version_precedente(client, db):
    offer = _offre(db, "Première lettre.")
    resp = client.patch(f"/api/offers/{offer.id}", json={"cover_letter": "Deuxième lettre."})
    data = resp.json()
    assert data["cover_letter"] == "Deuxième lettre."
    assert len(data["letter_versions"]) == 1
    assert data["letter_versions"][0]["texte"] == "Première lettre."


def test_lettre_vide_non_archivee(client, db):
    offer = _offre(db, "")
    resp = client.patch(f"/api/offers/{offer.id}", json={"cover_letter": "Première lettre."})
    assert resp.json()["letter_versions"] == []


def test_texte_identique_non_archive(client, db):
    offer = _offre(db, "Même texte.")
    client.patch(f"/api/offers/{offer.id}", json={"cover_letter": "Même texte."})
    assert client.get(f"/api/offers/{offer.id}").json()["letter_versions"] == []


def test_restauration_d_une_version(client, db):
    offer = _offre(db, "Version A.")
    client.patch(f"/api/offers/{offer.id}", json={"cover_letter": "Version B."})
    resp = client.post(f"/api/offers/{offer.id}/letter/restore/0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cover_letter"] == "Version A."
    # La version B est archivée à son tour : rien ne se perd.
    assert data["letter_versions"][0]["texte"] == "Version B."


def test_restauration_index_invalide(client, db):
    offer = _offre(db, "Version A.")
    assert client.post(f"/api/offers/{offer.id}/letter/restore/9").status_code == 404


def test_historique_plafonne(client, db):
    offer = _offre(db, "v0")
    for i in range(1, MAX_VERSIONS_LETTRE + 5):
        client.patch(f"/api/offers/{offer.id}", json={"cover_letter": f"v{i}"})
    versions = client.get(f"/api/offers/{offer.id}").json()["letter_versions"]
    assert len(versions) == MAX_VERSIONS_LETTRE
    assert versions[0]["texte"] == f"v{MAX_VERSIONS_LETTRE + 3}"  # la plus récente en tête
