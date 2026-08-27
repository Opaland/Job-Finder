"""Tests du digest (relances) et de l'extraction de description complète."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Offer, Profile, local_now
from app.services.digest import build_digest, digest_html, offers_to_relaunch
from app.services.enrich import extract_main_text


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    session.add(Profile(id=1, cv_text="cv", sources_enabled={}))
    session.commit()
    yield session
    session.close()


def _offer(db, status, days_ago, title="Test Manager"):
    changed = (local_now() - timedelta(days=days_ago)).isoformat()
    offer = Offer(
        fingerprint=f"fp-{title}-{status}-{days_ago}",
        source="test", source_id=f"{title}-{status}-{days_ago}",
        title=title, company="ACME", status=status, final_score=80,
        status_history=[{"status": status, "date": changed, "par": "utilisateur"}],
    )
    db.add(offer)
    db.commit()
    return offer


def test_relance_apres_7_jours(db):
    _offer(db, "postulee", days_ago=10, title="Vieille candidature")
    _offer(db, "postulee", days_ago=2, title="Candidature récente")
    _offer(db, "relancee", days_ago=8, title="Déjà relancée il y a longtemps")
    _offer(db, "entretien", days_ago=30, title="En entretien")  # pas concernée

    titles = [o.title for o in offers_to_relaunch(db)]
    assert "Vieille candidature" in titles
    assert "Déjà relancée il y a longtemps" in titles
    assert "Candidature récente" not in titles
    assert "En entretien" not in titles


def test_digest_contient_les_relances(db):
    _offer(db, "postulee", days_ago=10, title="À relancer")
    digest = build_digest(db)
    relaunch = digest.payload["to_relaunch"]
    assert len(relaunch) == 1
    assert relaunch[0]["title"] == "À relancer"
    # Et l'email les affiche.
    assert "relancer" in digest_html(digest.payload).lower()


def test_digest_sans_relance(db):
    _offer(db, "postulee", days_ago=1)
    digest = build_digest(db)
    assert digest.payload["to_relaunch"] == []


def test_actions_a_faire_aujourdhui(db):
    """Les actions datées échues (aujourd'hui + retard) remontent ; le futur non."""
    from app.models import Offer

    def offer_with_action(sid, days_offset, note):
        return Offer(
            fingerprint=f"fp-act-{sid}", source="test", source_id=f"act-{sid}",
            title=f"Offre {sid}", company="ACME", status="postulee", final_score=70,
            next_action_date=local_now() + timedelta(days=days_offset),
            next_action_note=note,
        )

    db.add_all([
        offer_with_action("retard", -3, "Relancer par email"),
        offer_with_action("jour", 0, "Préparer l'entretien"),
        offer_with_action("futur", 5, "Relance semaine prochaine"),
    ])
    db.commit()

    payload = build_digest(db).payload
    todo = {a["action_note"]: a for a in payload["todo_today"]}
    assert "Relancer par email" in todo and todo["Relancer par email"]["overdue"] is True
    assert "Préparer l'entretien" in todo and todo["Préparer l'entretien"]["overdue"] is False
    assert "Relance semaine prochaine" not in todo
    assert "faire aujourd" in digest_html(payload).lower()


def test_focus_du_jour(db):
    """Le focus priorise action échue > pépite > relance, sans doublon d'offre."""
    from app.models import Offer

    db.add_all([
        Offer(fingerprint="fp-f1", source="test", source_id="f1", title="Action due",
              company="A", status="postulee", final_score=60,
              next_action_date=local_now() - timedelta(days=1), next_action_note="Rappeler la RH"),
        Offer(fingerprint="fp-f2", source="test", source_id="f2", title="Pépite ouverte",
              company="B", status="nouvelle", final_score=93),
        Offer(fingerprint="fp-f3", source="test", source_id="f3", title="Vieille candidature",
              company="C", status="postulee", final_score=70,
              status_history=[{"status": "postulee", "date": (local_now() - timedelta(days=10)).isoformat(), "par": "u"}]),
    ])
    db.commit()

    focus = build_digest(db).payload["focus"]
    assert [f["type"] for f in focus] == ["action", "pepite", "relance"]
    assert focus[0]["label"].startswith("En retard")
    assert len({f["id"] for f in focus}) == len(focus)


def test_pepites_et_objectif_hebdo(db):
    """Les offres ouvertes >= 85 sont des pépites ; les candidatures de la semaine comptent."""
    from app.models import Offer

    gem = Offer(fingerprint="fp-gem", source="test", source_id="gem",
                title="Test Manager idéal", company="ACME", status="nouvelle", final_score=92)
    pas_gem = Offer(fingerprint="fp-bof", source="test", source_id="bof",
                    title="Offre moyenne", company="ACME", status="nouvelle", final_score=60)
    gem_traitee = Offer(fingerprint="fp-traitee", source="test", source_id="traitee",
                        title="Déjà postulée", company="ACME", status="postulee", final_score=95,
                        status_history=[{"status": "postulee", "date": local_now().isoformat(), "par": "utilisateur"}])
    db.add_all([gem, pas_gem, gem_traitee])
    db.commit()

    payload = build_digest(db).payload
    gem_titles = [g["title"] for g in payload["gems"]]
    assert "Test Manager idéal" in gem_titles
    assert "Offre moyenne" not in gem_titles
    assert "Déjà postulée" not in gem_titles  # déjà traitée : plus une pépite
    # Postulée aujourd'hui (donc cette semaine) → compte dans l'objectif.
    assert payload["weekly"]["sent"] >= 1
    assert payload["weekly"]["goal"] == 5  # défaut du profil


def test_extraction_texte_principal():
    html = """
    <html><head><script>var x=1;</script><style>.a{}</style></head>
    <body>
      <nav>Accueil Emploi Entreprises Connexion</nav>
      <div class="page">
        <aside>Publicité offres similaires</aside>
        <div class="offre">
          <h1>Test Manager H/F</h1>
          <p>%s</p>
          <p>Vous piloterez la stratégie de test, l'automatisation Selenium et KarateDSL,
          et encadrerez une équipe de testeurs dans un contexte santé ISO 13485.</p>
        </div>
      </div>
      <footer>Mentions légales</footer>
    </body></html>
    """ % ("Description détaillée du poste. " * 30)
    text = extract_main_text(html)
    assert "Test Manager H/F" in text
    assert "Selenium" in text
    assert "Mentions légales" not in text
    assert "var x=1" not in text


def test_header_annonce_preserve_mais_bandeau_site_retire():
    """<header> à l'intérieur de l'annonce = titre du poste (gardé) ; header du body = bandeau (retiré)."""
    html = """
    <html><body>
      <header>Bandeau du site · Connexion · Menu</header>
      <article>
        <header><h1>Responsable QA Lyon</h1></header>
        <p>%s</p>
      </article>
    </body></html>
    """ % ("Contenu détaillé de l'offre avec beaucoup de texte. " * 25)
    text = extract_main_text(html)
    assert "Responsable QA Lyon" in text
    assert "Bandeau du site" not in text


def test_enrich_reinitialise_avis_ia(db, monkeypatch):
    """Après enrichissement, l'avis IA (calculé sur l'ancien extrait) est retiré."""
    from fastapi.testclient import TestClient

    import app.routers.offers as offers_router
    from app.database import get_db
    from app.main import app as fastapi_app

    offer = Offer(
        fingerprint="fp-enrich", source="test", source_id="enrich-1",
        title="Test Manager", company="ACME", description="Extrait court.",
        url="https://example.com/offre", score=60, final_score=45,
        ai_score=30.0, ai_reason="Description trop vague.",
    )
    db.add(offer)
    db.commit()

    long_text = "Description complète du poste de Test Manager, Selenium, management. " * 10
    monkeypatch.setattr(offers_router, "fetch_full_description", lambda url: long_text)
    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        resp = client.post(f"/api/offers/{offer.id}/enrich")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ai_score"] is None
        assert data["ai_reason"] == ""
        assert data["description"].startswith("Description complète")
        assert data["final_score"] == data["score"]
    finally:
        fastapi_app.dependency_overrides.clear()


def test_titres_echappes_dans_l_email(db):
    """Un titre contenant « & » ou « <…> » ne doit pas casser l'email."""
    db.add(Offer(
        fingerprint="fp-html", source="france_travail", source_id="html-1",
        title="Test Manager <H/F> R&D", company="ACME & Fils", location="Lyon",
        url="https://exemple.fr/offre?a=1&b=2", final_score=90.0, score=90.0,
        status="nouvelle",
    ))
    db.commit()

    html = digest_html(build_digest(db).payload)
    assert "Test Manager &lt;H/F&gt; R&amp;D" in html
    assert "ACME &amp; Fils" in html
    assert "<H/F>" not in html


def test_le_decor_de_page_n_est_pas_pris_pour_une_offre():
    """Une page rendue côté client (APEC) ne livre que son bandeau cookies.
    Il faisait 417 caractères contre 283 pour le vrai résumé : l'enrichissement
    l'écrasait, et remettait l'avis IA à zéro au passage."""
    from app.services.enrich import ressemble_a_une_offre

    bandeau = (
        "Les informations légales ont changé\nJ'ai pris connaissance des\n"
        "informations légales\nque ce soit les conditions générales d'utilisation, "
        "la Politique de protection de données à caractère personnel ainsi que la "
        "gestion des cookies et je les accepte.\nVous devez accepter les informations "
        "légales\nUne erreur inattendue est survenue. Merci de réessayer ultérieurement."
    )
    assert ressemble_a_une_offre(bandeau) is False


def test_une_vraie_annonce_est_acceptee():
    from app.services.enrich import ressemble_a_une_offre

    annonce = (
        "Test Manager : en un coup d'oeil. Premier éditeur français de cybersécurité, "
        "nous recherchons un Test Manager pour piloter la stratégie de test de nos "
        "produits. Vous animerez une équipe QA, définirez le plan de test, suivrez la "
        "couverture et l'automatisation Selenium et Cypress, et travaillerez avec les "
        "équipes de développement en méthode agile. Environnement CI/CD GitLab, Jira, "
        "tests API. Poste basé à Lyon, télétravail 3 jours par semaine. "
    ) * 2
    assert ressemble_a_une_offre(annonce) is True


def test_une_annonce_qui_mentionne_les_conditions_generales_en_bas_reste_acceptee():
    """Le décor se reconnaît EN TÊTE : on ne rejette pas une vraie annonce
    parce qu'elle cite les conditions générales dans son pied de page."""
    from app.services.enrich import ressemble_a_une_offre

    annonce = ("Nous recherchons un Test Manager expérimenté pour piloter notre "
               "stratégie qualité. " * 12) + "\nMentions et conditions générales d'utilisation."
    assert ressemble_a_une_offre(annonce) is True


# --- Le bandeau de cookies pris pour une offre (régression c60ba8c) ----------
#
# Les trois tests précédents n'éprouvent que `ressemble_a_une_offre`. Les deux
# suivants passent par le VRAI chemin de code — celui qui portait le défaut :
# `fetch_full_description`, puis la route d'enrichissement. Sans eux, remplacer
# le garde-fou par le `len(text) >= 300` d'origine laissait la suite verte.

BANDEAU_APEC = (
    "J'ai pris connaissance des informations légales, que ce soit les conditions "
    "générales d'utilisation, la Politique de protection de données à caractère "
    "personnel ainsi que la gestion des cookies, et je les accepte. Vous devez "
    "accepter les informations légales pour continuer votre navigation sur le site. "
    "Une erreur inattendue est survenue. Merci de réessayer ultérieurement. "
    "Veuillez activer JavaScript dans votre navigateur pour accéder à cette page."
)
PAGE_BANDEAU = f"<html><body><div><p>{BANDEAU_APEC}</p></div></body></html>"

# 283 caractères : la longueur exacte à laquelle l'API de l'APEC tronque son
# résumé. Le bandeau étant plus long, le garde « déjà aussi complet » (409) ne
# protège pas — c'est tout le sujet.
RESUME_TRONQUE = "Nous recherchons un Lead QA pour piloter la stratégie de test. " * 4 + "Fin."


class _ReponsePage:
    def __init__(self, html):
        self.text = html
        self.headers = {"content-type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        return None


class _ClientPage:
    def __init__(self, html):
        self._html = html

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, **_):
        return _ReponsePage(self._html)


@pytest.fixture()
def page_servie(monkeypatch):
    """Sert un HTML donné à `fetch_full_description`, sans réseau."""
    from app.services import enrich as enrich_module

    def brancher(html):
        monkeypatch.setattr(enrich_module, "client_http", lambda timeout=20: _ClientPage(html))
    return brancher


def test_le_bandeau_de_cookies_ne_devient_pas_une_description(page_servie):
    from app.services.enrich import extract_main_text, fetch_full_description

    # Le bandeau dépasse le seuil de longueur : seul le garde-fou peut le refuser.
    assert len(extract_main_text(PAGE_BANDEAU)) > 300
    page_servie(PAGE_BANDEAU)
    assert fetch_full_description("https://www.apec.fr/offre/1") is None


def test_une_vraie_page_d_offre_est_bien_recuperee(page_servie):
    """Le garde-fou ne doit pas non plus tout refuser."""
    from app.services.enrich import fetch_full_description

    annonce = ("Vous piloterez la stratégie de test d'une plateforme critique : plan "
               "de test, animation de l'équipe QA, automatisation Selenium. " * 6)
    page_servie(f"<html><body><article><p>{annonce}</p></article></body></html>")
    texte = fetch_full_description("https://www.hellowork.com/fr-fr/emplois/1.html")
    assert texte is not None and "stratégie de test" in texte


def test_une_page_qui_reclame_javascript_est_rejetee(page_servie):
    """Autre visage du même défaut : la page ne dit pas « cookies » mais
    « activez JavaScript ». Sans ce cas, retirer ces marqueurs de la liste
    passait inaperçu."""
    from app.services.enrich import fetch_full_description

    ecran = ("Cette page nécessite JavaScript pour fonctionner correctement. "
             "Veuillez activer JavaScript dans les paramètres de votre navigateur, "
             "puis recharger la page pour consulter cette annonce. " * 3)
    page_servie(f"<html><body><div><p>{ecran}</p></div></body></html>")
    assert fetch_full_description("https://www.exemple.fr/offre/1") is None


def test_l_enrichissement_refuse_le_bandeau_et_preserve_l_avis_ia(db, page_servie):
    """Le scénario complet : sans le garde-fou, la description réelle était
    remplacée par le bandeau ET l'avis IA repartait à zéro — deux pertes
    irrécupérables, l'utilisateur n'ayant aucun moyen de revenir en arrière."""
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app
    from app.routers.offers import get_db

    offer = Offer(
        fingerprint="fp-bandeau", source="apec", source_id="bandeau-1",
        title="Lead QA", company="O2MAX", description=RESUME_TRONQUE,
        url="https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/1",
        score=60, final_score=45, ai_score=30.0, ai_reason="Avis existant.",
    )
    db.add(offer)
    db.commit()
    page_servie(PAGE_BANDEAU)

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        reponse = TestClient(fastapi_app).post(f"/api/offers/{offer.id}/enrich")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert reponse.status_code == 502
    db.refresh(offer)
    assert offer.description == RESUME_TRONQUE
    assert offer.ai_score == 30.0
    assert offer.ai_reason == "Avis existant."
