"""Tests sur les VRAIES sources — aucun client bouchonné, aucun monkeypatch.

Un test qui interroge un faux client prouve qu'on envoie ce qu'on croit envoyer.
Il ne prouve pas que la source l'accepte, ni qu'elle répond ce qu'on attend.
Les trois défauts de la V1 (filtre géographique ignoré, lien de l'offre en 404,
bandeau de cookies pris pour une description) étaient tous de cette nature :
invisibles tant qu'on ne parlait pas au vrai site.

Ce fichier appelle donc réellement apec.fr et hellowork.com. Trois issues :

  - la source répond et le contrat est tenu    → vert ;
  - la source répond et le contrat est rompu   → ROUGE, c'est tout l'intérêt ;
  - la source est injoignable (réseau, 403…)   → ignoré, avec la raison.

La troisième règle est délibérée : une coupure réseau n'est pas une régression
du code, et la faire passer pour telle apprendrait à ignorer le rouge. En
revanche, une source qui répond sans erreur ET sans offre fait ÉCHOUER le test —
c'est le « succès à vide » que tout le diagnostic cherche à débusquer.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors import ALL_CONNECTORS
from app.connectors.apec import ApecConnector
from app.connectors.base import client_http
from app.connectors.hellowork import HelloWorkConnector
from app.database import Base
from app.models import Offer, Profile, local_now
from app.services.diagnostic import diagnostiquer_source, verdict
from app.services.enrich import fetch_full_description

PROFIL = {"search_queries": ["test manager", "QA", "responsable test"]}

# Départements du bassin lyonnais, tels qu'ils apparaissent en fin de lieu
# (« Lyon 01 - 69 », « Bourgoin-Jallieu - 38 »).
BASSIN_LYONNAIS = ("69", "01", "1", "38", "42")
# Les recherches lyonnaises pèsent 4 requêtes sur 5, la cinquième est la
# recherche nationale en télétravail : une majorité franche doit rester
# lyonnaise. Mesuré à 74 % le 27/08/2026 ; c'était 5 % avec le filtre
# géolocalisé que ce seuil protège.
PART_LYONNAISE_MINIMALE = 0.6


def _offres(resultat, source: str) -> list:
    """Les offres, ou la bonne raison de ne pas conclure."""
    if resultat.offers:
        return resultat.offers
    if resultat.errors:
        pytest.skip(f"{source} injoignable : {resultat.errors[0]}")
    pytest.fail(
        f"{source} a répondu sans erreur et sans aucune offre — c'est exactement "
        f"le « succès à vide » que la V1 cherche à rendre visible."
    )


@pytest.fixture(scope="module")
def apec():
    return _offres(ApecConnector().fetch(PROFIL), "APEC")


@pytest.fixture(scope="module")
def hellowork():
    return _offres(HelloWorkConnector().fetch(PROFIL), "HelloWork")


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/reel.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(Profile(id=1, cv_text="cv", sources_enabled={}))
    session.commit()
    yield session
    session.close()


# --- APEC --------------------------------------------------------------------

# Sans ces trois-là une offre n'est pas exploitable du tout — et le connecteur
# refuse déjà de la construire. Exigence : 100 %.
CHAMPS_INDISPENSABLES = ("title", "url", "source_id")
# Ceux-là peuvent manquer sur une annonce ISOLÉE en toute légitimité : l'APEC
# publie des offres confidentielles (« nomCommercial » vide), et une annonce
# peut taire son lieu. Ce que le diagnostic traque, c'est le champ vide sur
# TOUTES les offres — la signature d'un mapping cassé. Le seuil laisse passer
# l'exception sans laisser passer la panne : mesuré à 1 offre sur 169.
# `description` en fait partie plutôt que d'être exigée à 100 % : c'est ce que
# lisent le scoring et l'IA, et le seuil la protège tout aussi bien (une
# description cassée s'effondrerait bien en dessous de 90 %). Relevé du jour :
# APEC 169/169, HelloWork 57/57 — seule `company` descend à 168/169.
CHAMPS_PRESQUE_TOUJOURS = ("company", "location", "description")
PART_REMPLIE_MINIMALE = 0.9


def _verifier_remplissage(offres, source: str) -> None:
    for champ in CHAMPS_INDISPENSABLES:
        manquants = [o for o in offres if not (getattr(o, champ) or "").strip()]
        assert not manquants, f"{source} : {champ} vide sur {len(manquants)}/{len(offres)} offres"

    for champ in CHAMPS_PRESQUE_TOUJOURS:
        remplis = sum(1 for o in offres if (getattr(o, champ) or "").strip())
        part = remplis / len(offres)
        assert part >= PART_REMPLIE_MINIMALE, (
            f"{source} : {champ} rempli sur {part:.0%} des offres seulement "
            f"({remplis}/{len(offres)}) — le mapping ne correspond plus à la réponse. "
            f"Exemples : {[o.title for o in offres if not (getattr(o, champ) or '').strip()][:3]}"
        )


def test_apec_remplit_tous_les_champs_essentiels(apec):
    """Le danger n'est pas la panne, c'est la source qui réussit à vide : un
    champ renommé et l'offre arrive sans entreprise, sans que rien ne le dise."""
    _verifier_remplissage(apec, "APEC")


def test_les_offres_apec_restent_dans_le_bassin_lyonnais(apec):
    """Régression df71b55 : avec `pointGeolocDeReference` et `distance`, une
    recherche « Lyon » renvoyait Nantes, Saran et Annemasse — 1 offre sur 20
    dans le Rhône. Seul le filtre par département tient."""
    lyonnaises = [
        o for o in apec
        if (o.location or "").rsplit("-", 1)[-1].strip() in BASSIN_LYONNAIS
    ]
    part = len(lyonnaises) / len(apec)
    assert part >= PART_LYONNAISE_MINIMALE, (
        f"{part:.0%} des offres APEC sont lyonnaises (seuil {PART_LYONNAISE_MINIMALE:.0%}) — "
        f"le filtre par département ne mord plus. Exemples hors bassin : "
        f"{[o.location for o in apec if o not in lyonnaises][:5]}"
    )


def test_le_lien_d_une_offre_apec_ouvre_vraiment_la_page(apec):
    """Régression c60ba8c : la forme au pluriel renvoyait 404 sur 100 % des
    offres. Personne ne s'en aperçoit avant d'avoir cliqué — donc on clique."""
    with client_http(timeout=20) as client:
        reponse = client.get(apec[0].url)
    assert reponse.status_code == 200, (
        f"{apec[0].url} répond {reponse.status_code} : le lien de chaque offre "
        f"APEC est mort dans l'interface."
    )


def test_les_contrats_apec_ne_sont_jamais_des_codes(apec):
    """`typeContrat` est un CODE numérique. Injecté tel quel, le scoring n'y
    voit pas un CDI — et l'utilisateur lit « 101888 » dans l'interface."""
    codes = sorted({o.contract_type for o in apec if o.contract_type.isdigit()})
    assert not codes, f"codes bruts affichés comme contrats : {codes}"


def test_les_dates_apec_ne_sont_jamais_dans_le_futur(apec):
    """L'APEC répond en UTC : mal convertie, une offre du soir se retrouve au
    mauvais jour, et le tri « les plus récentes » ment."""
    demain = local_now() + timedelta(days=1)
    futures = [o.title for o in apec if o.published_at and o.published_at > demain]
    assert not futures, f"offres datées dans le futur : {futures[:3]}"


def test_la_date_apec_est_bien_convertie_en_heure_de_paris():
    """L'APEC répond en « +0000 ». Retirer le fuseau sans CONVERTIR décale de
    deux heures — et fait changer de jour toute offre publiée après 22 h UTC,
    donc changer de place dans le tri « les plus récentes ».

    On recalcule ici l'heure attendue par un autre chemin (zoneinfo, à partir de
    la valeur brute de l'API) que celui du code testé."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.config import settings
    from app.connectors.apec import SEARCH_URL
    from app.connectors.base import parse_published

    with client_http(timeout=20) as client:
        reponse = client.post(SEARCH_URL, json=ApecConnector.payloads(PROFIL)[0])
    if reponse.status_code != 200:
        pytest.skip(f"APEC répond {reponse.status_code}")
    resultats = reponse.json().get("resultats") or []
    if not resultats:
        pytest.skip("APEC n'a renvoyé aucune offre à dater")

    brutes = [o["datePublication"] for o in resultats if o.get("datePublication")]
    assert brutes, "aucune datePublication dans la réponse APEC"
    for brute in brutes[:10]:
        avec_fuseau = datetime.fromisoformat(brute.replace("Z", "+00:00"))
        attendue = avec_fuseau.astimezone(ZoneInfo(settings.timezone)).replace(tzinfo=None)
        assert parse_published(brute) == attendue, (
            f"{brute} lue {parse_published(brute)} au lieu de {attendue} "
            f"(heure de {settings.timezone})"
        )


def test_l_apec_donne_au_moins_une_offre_recente(apec):
    """Si toutes les dates étaient perdues ou fausses, le tri par fraîcheur et
    la détection des annonces fantômes ne serviraient plus à rien."""
    datees = [o for o in apec if o.published_at]
    assert datees, "aucune offre APEC datée"
    plus_recente = max(o.published_at for o in datees)
    assert plus_recente > local_now() - timedelta(days=15), (
        f"l'offre APEC la plus récente date du {plus_recente:%d/%m/%Y}"
    )


# --- HelloWork ---------------------------------------------------------------

def test_hellowork_remplit_tous_les_champs_essentiels(hellowork):
    """La fixture figée ne peut pas voir une refonte du site : ce test, si."""
    _verifier_remplissage(hellowork, "HelloWork")


def test_hellowork_date_toutes_ses_offres(hellowork):
    """« il y a 13 jours » et « plus de 1 mois » doivent être compris tous les
    deux : la seconde forme manquait, et l'offre perdait sa date."""
    sans_date = [o.title for o in hellowork if o.published_at is None]
    assert not sans_date, f"offres HelloWork sans date : {sans_date[:3]}"


def test_les_dates_hellowork_ne_sont_jamais_dans_le_futur(hellowork):
    """« il y a 13 jours » se compte en ARRIÈRE. Le signe inversé datait les
    offres du futur, et l'offre la plus vieille remontait en tête du tri par
    fraîcheur — sans qu'aucune date ne paraisse absurde à l'écran."""
    demain = local_now() + timedelta(days=1)
    futures = [(o.title, o.published_at) for o in hellowork if o.published_at > demain]
    assert not futures, f"offres HelloWork datées dans le futur : {futures[:3]}"


def test_la_recherche_teletravail_de_hellowork_ramene_du_teletravail():
    """Régression : « l=Télétravail » répond 200 avec « 0 offre » — deux des
    cinq recherches tournaient à vide sans qu'aucune erreur ne le signale.
    On interroge donc la vraie URL du filtre dédié."""
    _, url = HelloWorkConnector.recherches({"search_queries": ["test"]})[-1]
    with client_http(timeout=20) as client:
        reponse = client.get(url)
    if reponse.status_code != 200:
        pytest.skip(f"HelloWork répond {reponse.status_code} sur {url}")

    offres = HelloWorkConnector()._parse_page(reponse.text)
    assert offres, f"{url} ne ramène aucune offre : le filtre télétravail ne mord plus"
    assert all(o.remote for o in offres), (
        "des offres du filtre « télétravail complet » ne sont pas marquées remote : "
        f"{[o.title for o in offres if not o.remote][:3]}"
    )


def test_hellowork_conserve_les_salaires_affiches(hellowork):
    """Le salaire est sur la carte ; il était jeté. C'est le seul montant que
    cette source donne, et le scoring en tient compte."""
    avec_salaire = [o for o in hellowork if o.salary_text]
    assert avec_salaire, "aucune offre HelloWork ne porte de salaire"
    assert all("€" in o.salary_text for o in avec_salaire)


def test_la_page_reelle_reste_conforme_a_la_fixture():
    """Garde-fou anti-péremption : la fixture figée est un extrait d'une page
    réelle. Si le site change de structure, la fixture continue de passer au
    vert toute seule — celui-ci, non."""
    _, url = HelloWorkConnector.recherches({"search_queries": ["test manager"]})[0]
    with client_http(timeout=20) as client:
        reponse = client.get(url)
    if reponse.status_code != 200:
        pytest.skip(f"HelloWork répond {reponse.status_code}")

    offres = HelloWorkConnector()._parse_page(reponse.text)
    assert offres, "la page de résultats réelle ne donne plus aucune offre"
    premiere = offres[0]
    assert premiere.title and premiere.company and premiere.location
    assert premiere.url.startswith("https://www.hellowork.com/fr-fr/emplois/")


# --- Enrichissement, sur de vraies pages -------------------------------------

def test_une_vraie_page_hellowork_est_enrichie(hellowork):
    """Le seul enrichissement qui marche vraiment aujourd'hui : la page
    HelloWork rend son texte côté serveur."""
    texte = fetch_full_description(hellowork[0].url)
    if texte is None:
        pytest.skip(f"page {hellowork[0].url} indisponible")
    assert len(texte) > 1000, f"seulement {len(texte)} caractères extraits"
    assert len(texte) > len(hellowork[0].description)


def test_une_vraie_page_apec_ne_livre_que_son_bandeau(apec):
    """Régression c60ba8c, sur la vraie page : l'APEC est rendue côté client,
    et ne renvoie que 417 caractères de bandeau cookies — PLUS LONGS que le
    résumé réel de 283 caractères. Sans garde-fou, l'enrichissement écrasait la
    vraie description et remettait l'avis IA à zéro."""
    assert fetch_full_description(apec[0].url) is None, (
        "l'APEC livre maintenant un vrai texte : le garde-fou reste utile, mais "
        "le connecteur peut enfin récupérer la description complète."
    )


def test_l_enrichissement_d_une_page_apec_preserve_l_avis_ia(db, apec):
    """Le scénario complet, de bout en bout, sans rien simuler : la route doit
    refuser, et surtout ne rien détruire. La description et l'avis IA sont
    irrécupérables — l'utilisateur n'a aucun moyen de revenir en arrière."""
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app
    from app.routers.offers import get_db

    resume = apec[0].description
    offre = Offer(
        fingerprint="fp-reel-apec", source="apec", source_id=apec[0].source_id,
        title=apec[0].title, company=apec[0].company, description=resume,
        url=apec[0].url, score=60, final_score=45,
        ai_score=30.0, ai_reason="Avis existant.",
    )
    db.add(offre)
    db.commit()

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        reponse = TestClient(fastapi_app).post(f"/api/offers/{offre.id}/enrich")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert reponse.status_code == 502, reponse.text
    db.refresh(offre)
    assert offre.description == resume
    assert offre.ai_score == 30.0
    assert offre.ai_reason == "Avis existant."


def test_l_enrichissement_d_une_page_hellowork_remet_l_avis_ia_a_zero(db, hellowork):
    """L'autre moitié du contrat : quand l'enrichissement réussit, l'avis IA
    portait sur l'ancien extrait et doit être recalculé, pas conservé."""
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app
    from app.routers.offers import get_db

    offre = Offer(
        fingerprint="fp-reel-hw", source="hellowork", source_id=hellowork[0].source_id,
        title=hellowork[0].title, company=hellowork[0].company,
        description=hellowork[0].description, url=hellowork[0].url,
        score=60, final_score=45, ai_score=30.0, ai_reason="Description trop vague.",
    )
    db.add(offre)
    db.commit()

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        reponse = TestClient(fastapi_app).post(f"/api/offers/{offre.id}/enrich")
    finally:
        fastapi_app.dependency_overrides.clear()

    if reponse.status_code == 502:
        pytest.skip(f"page {offre.url} indisponible")
    assert reponse.status_code == 200, reponse.text
    donnees = reponse.json()
    assert len(donnees["description"]) > 1000
    assert donnees["ai_score"] is None
    assert donnees["ai_reason"] == ""
    assert donnees["final_score"] == donnees["score"]


# --- Les sources à clé -------------------------------------------------------
#
# Tant que le .env est vide, ces tests s'ignorent en NOMMANT les variables qui
# manquent. Le jour où une clé est renseignée, la source est éprouvée pour de
# vrai sans rien avoir à activer : c'est le retour immédiat qui manque quand on
# vient de coller une clé et qu'on se demande si elle marche.

@pytest.mark.parametrize("connecteur", [c for c in ALL_CONNECTORS if c.needs_key],
                         ids=lambda c: c.name)
def test_une_source_a_cle_configuree_tient_son_contrat(connecteur):
    """Même exigence que pour l'APEC : répondre, et remplir ses champs.

    `diagnostiquer_source` est le code que la commande `sources` utilise déjà —
    on éprouve donc aussi le diagnostic sur du vrai, pas seulement le connecteur.
    """
    if not connecteur.is_configured():
        pytest.skip(f"{connecteur.label} : {_cles_manquantes(connecteur)}")

    resultat = diagnostiquer_source(connecteur, PROFIL)
    etat, explication = verdict(resultat)

    if etat == "ko":
        pytest.skip(f"{connecteur.label} injoignable : {explication}")
    assert etat == "ok", f"{connecteur.label} — {explication}"
    assert not resultat["champs_vides"], (
        f"{connecteur.label} remplit mal : {resultat['champs_vides']}"
    )


def _cles_manquantes(connecteur) -> str:
    """Le connecteur nomme lui-même ses variables d'environnement."""
    resultat = connecteur.fetch({})
    return resultat.errors[0] if resultat.errors else "clé absente du .env"


# --- Le scan complet, sur les vraies sources ---------------------------------

def test_un_vrai_scan_collecte_score_et_ne_touche_a_aucun_statut(tmp_path, monkeypatch):
    """Le test de bout en bout : les vraies sources, le vrai dédoublonnage, le
    vrai scoring, sur une base jetable.

    L'affinage IA est mis à zéro par `ai_max_offers_per_scan` — c'est un
    réglage prévu, pas un bouchon : 15 appels à la CLI Claude à chaque
    `verif.sh` coûteraient des minutes et des jetons pour ne rien prouver de
    plus sur les sources.

    On vérifie surtout la règle absolue du projet : **un scan ne ferme, ne
    supprime ni ne change jamais le statut d'une offre.**
    """
    from app.config import settings
    from app.models import STATUTS_CLOS, ScanRun
    from app.services.scan import run_scan
    from app.services.seeding import ensure_profile

    monkeypatch.setattr(settings, "ai_max_offers_per_scan", 0)

    moteur = create_engine(f"sqlite:///{tmp_path}/scan-reel.db")
    Base.metadata.create_all(moteur)
    db = sessionmaker(bind=moteur, expire_on_commit=False)()
    try:
        ensure_profile(db)
        db.commit()

        # Une offre déjà suivie, dans un statut que l'utilisateur a posé lui-même.
        suivie = Offer(
            fingerprint="fp-deja-suivie", source="apec", source_id="deja-suivie",
            title="Test Manager déjà suivi", company="ACME", location="Lyon",
            url="https://exemple.fr/offre-suivie", status=STATUTS_CLOS[0],
            score=70, final_score=70, collected_at=local_now(), last_seen_at=local_now(),
        )
        db.add(suivie)
        db.commit()

        run = run_scan(db, trigger="test")

        assert isinstance(run, ScanRun)
        assert run.status == "termine", f"scan en {run.status}"
        if run.new_count == 0 and run.seen_count == 0:
            pytest.skip(f"aucune source joignable pendant le scan : {run.source_stats}")

        offres = db.query(Offer).filter(Offer.source_id != "deja-suivie").all()
        assert offres, "le scan n'a enregistré aucune offre"
        assert all(o.score is not None and o.final_score is not None for o in offres), (
            "des offres sont arrivées sans score"
        )
        assert all(0 <= o.score <= 100 for o in offres)

        # Le dédoublonnage : deux offres ne peuvent pas partager une empreinte.
        empreintes = [o.fingerprint for o in offres]
        assert len(empreintes) == len(set(empreintes))

        # La règle absolue.
        db.refresh(suivie)
        assert suivie.status == STATUTS_CLOS[0], "le scan a changé le statut d'une offre"
        assert db.get(Offer, suivie.id) is not None, "le scan a supprimé une offre"
    finally:
        db.close()


# --- L'IA : la vraie CLI locale ----------------------------------------------

def test_la_cli_claude_repond_bien_du_json_quand_elle_est_installee():
    """L'IA du projet passe par la CLI `claude` locale, jamais par une clé API.
    Ce que les tests unitaires ne peuvent pas prouver : que le contrat avec
    l'outil externe (une réponse JSON exploitable) tient encore.

    Ignoré quand la CLI n'est pas installée — c'est le cas de la CI, et c'est
    précisément le repli que le code prévoit."""
    from app.services.claude_ai import _extract_json, _run_claude, cli_available

    if not cli_available():
        pytest.skip("CLI `claude` absente — le repli 503 est testé sans elle")

    brut = _run_claude(
        'Réponds UNIQUEMENT par ce JSON, sans rien autour : {"score": 42, "raison": "test"}',
        timeout=120,
    )
    assert brut is not None, "la CLI `claude` n'a rien renvoyé"
    donnees = _extract_json(brut)
    assert donnees is not None, f"réponse non exploitable : {brut[:200]!r}"
    assert donnees.get("score") == 42
