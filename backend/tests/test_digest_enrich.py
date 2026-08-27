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


def test_une_page_qui_reclame_javascript_n_est_pas_une_offre():
    """Autre visage du même défaut : la page ne parle pas de cookies mais
    réclame JavaScript. Sans ce cas, retirer ces marqueurs de la liste passait
    inaperçu — le message d'attente devenait la description de l'offre."""
    from app.services.enrich import ressemble_a_une_offre

    ecran = ("Cette page nécessite JavaScript pour fonctionner correctement. "
             "Veuillez activer JavaScript dans les paramètres de votre navigateur, "
             "puis recharger la page pour consulter cette annonce. " * 3)
    assert ressemble_a_une_offre(ecran) is False


def test_une_annonce_qui_mentionne_les_conditions_generales_en_bas_reste_acceptee():
    """Le décor se reconnaît EN TÊTE : on ne rejette pas une vraie annonce
    parce qu'elle cite les conditions générales dans son pied de page."""
    from app.services.enrich import ressemble_a_une_offre

    annonce = ("Nous recherchons un Test Manager expérimenté pour piloter notre "
               "stratégie qualité. " * 12) + "\nMentions et conditions générales d'utilisation."
    assert ressemble_a_une_offre(annonce) is True


# --- La route d'enrichissement, sur de vraies requêtes HTTP -------------------
#
# Le chemin complet (route → fetch_full_description → httpx → extract_main_text
# → garde-fou) doit être vérifiable sans dépendre d'apec.fr. On sert donc les
# deux pages depuis un VRAI serveur HTTP local : rien n'est bouchonné, et le
# résultat ne dépend ni du réseau ni de l'humeur d'un site tiers.
#
# Bouchonner `fetch_full_description`, c'est court-circuiter précisément la
# fonction qui portait le défaut — c'est ce que faisait l'ancien test, et c'est
# pour ça qu'il n'a rien vu.

# Bandeau réel de l'APEC : 417 caractères, PLUS LONGS que le résumé de 283
# caractères fourni par son API. Le garde « déjà aussi complet » ne protège donc
# pas — c'est tout le sujet.
BANDEAU_APEC = (
    "J'ai pris connaissance des informations légales, que ce soit les conditions "
    "générales d'utilisation, la Politique de protection de données à caractère "
    "personnel ainsi que la gestion des cookies, et je les accepte. Vous devez "
    "accepter les informations légales pour continuer votre navigation sur le site. "
    "Une erreur inattendue est survenue. Merci de réessayer ultérieurement. "
    "Veuillez activer JavaScript dans votre navigateur pour accéder à cette page."
)
ANNONCE_COMPLETE = (
    "Vous piloterez la stratégie de test d'une plateforme critique : rédaction du "
    "plan de test, animation de l'équipe QA, automatisation Selenium et Cypress, "
    "intégration continue, suivi des anomalies sous Jira. " * 8
)
# 283 caractères : la longueur exacte à laquelle l'API de l'APEC tronque son résumé.
RESUME_TRONQUE = "Nous recherchons un Lead QA pour piloter la stratégie de test. " * 4 + "Fin."

PAGES = {
    "/bandeau": f"<html><body><div><p>{BANDEAU_APEC}</p></div></body></html>",
    "/annonce": f"<html><body><article><p>{ANNONCE_COMPLETE}</p></article></body></html>",
}


@pytest.fixture(scope="module")
def serveur_de_pages():
    """Un vrai serveur HTTP local, le temps du module."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            corps = PAGES.get(self.path, "<html><body>introuvable</body></html>").encode("utf-8")
            self.send_response(200 if self.path in PAGES else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *_):
            pass                                  # pas de bruit dans la sortie des tests

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _offre_enrichie(db, url, description):
    offre = Offer(
        fingerprint=f"fp-{url[-8:]}", source="apec", source_id=url[-8:],
        title="Lead QA", company="O2MAX", description=description, url=url,
        score=60, final_score=45, ai_score=30.0, ai_reason="Avis existant.",
    )
    db.add(offre)
    db.commit()
    return offre


def _enrichir(db, offre):
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app
    from app.routers.offers import get_db

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        return TestClient(fastapi_app).post(f"/api/offers/{offre.id}/enrich")
    finally:
        fastapi_app.dependency_overrides.clear()


def test_le_bandeau_de_cookies_ne_remplace_pas_la_description(db, serveur_de_pages):
    """Sans le garde-fou, la description réelle était remplacée par le bandeau
    ET l'avis IA repartait à zéro — deux pertes irrécupérables, l'utilisateur
    n'ayant aucun moyen de revenir en arrière."""
    offre = _offre_enrichie(db, f"{serveur_de_pages}/bandeau", RESUME_TRONQUE)

    reponse = _enrichir(db, offre)

    assert reponse.status_code == 502, reponse.text
    db.refresh(offre)
    assert offre.description == RESUME_TRONQUE
    assert offre.ai_score == 30.0
    assert offre.ai_reason == "Avis existant."


def test_une_vraie_annonce_remplace_la_description_et_remet_l_avis_ia_a_zero(db, serveur_de_pages):
    """L'autre moitié du contrat : le garde-fou ne doit pas tout refuser, et
    l'avis IA portait sur l'ancien extrait — il est recalculé, pas conservé."""
    offre = _offre_enrichie(db, f"{serveur_de_pages}/annonce", "Extrait court.")

    reponse = _enrichir(db, offre)

    assert reponse.status_code == 200, reponse.text
    donnees = reponse.json()
    assert "stratégie de test" in donnees["description"]
    assert donnees["ai_score"] is None
    assert donnees["ai_reason"] == ""
    assert donnees["final_score"] == donnees["score"]


def test_une_page_introuvable_laisse_l_offre_intacte(db, serveur_de_pages):
    """Un 404 sur la page d'origine ne doit rien abîmer non plus."""
    offre = _offre_enrichie(db, f"{serveur_de_pages}/disparue", RESUME_TRONQUE)

    assert _enrichir(db, offre).status_code == 502
    db.refresh(offre)
    assert offre.description == RESUME_TRONQUE
    assert offre.ai_score == 30.0
