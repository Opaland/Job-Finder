"""Diagnostic des sources (V1) : détecter une source qui « réussit à vide ».

Le cas dangereux n'est pas le connecteur qui plante — c'est celui qui répond
sans erreur en renvoyant des offres inexploitables.
"""
import httpx
import pytest

from app.connectors.base import (
    ConnectorResult,
    RawOffer,
    _enregistrer_reponse,
    capture_reponses,
    resume_erreur,
)
from app.services.diagnostic import diagnostiquer_source, rapport_texte, verdict


class FausseSource:
    name = "faux"
    label = "Source de test"

    def __init__(self, resultat, configure=True):
        self._resultat = resultat
        self._configure = configure

    def is_configured(self):
        return self._configure

    def fetch(self, profile):
        if isinstance(self._resultat, Exception):
            raise self._resultat
        return self._resultat


def _offre(**champs):
    base = dict(
        source="faux", source_id="1", title="Test Manager", company="ACME",
        location="Lyon", description="Une vraie description.", url="https://ex.fr/1",
    )
    base.update(champs)
    return RawOffer(**base)


def test_source_saine_est_ok():
    resultat = diagnostiquer_source(FausseSource(ConnectorResult(offers=[_offre()])), {})
    etat, explication = verdict(resultat)
    assert etat == "ok"
    assert "1 offre" in explication


def test_champ_vide_sur_toutes_les_offres_est_suspect():
    """Le scan dirait « tout va bien » : c'est exactement ce qu'on veut voir ici."""
    offres = [_offre(source_id="1", company=""), _offre(source_id="2", company="  ")]
    resultat = diagnostiquer_source(FausseSource(ConnectorResult(offers=offres)), {})
    etat, explication = verdict(resultat)
    assert etat == "suspect"
    assert "company" in explication
    assert resultat["champs_vides"] == ["company"]


def test_un_champ_vide_sur_une_seule_offre_ne_declenche_rien():
    offres = [_offre(source_id="1", company=""), _offre(source_id="2", company="ACME")]
    resultat = diagnostiquer_source(FausseSource(ConnectorResult(offers=offres)), {})
    assert resultat["champs_vides"] == []
    assert verdict(resultat)[0] == "ok"


def test_remote_false_partout_n_est_pas_une_alerte():
    """Régression : « aucune offre en télétravail » est un résultat normal à Lyon,
    pas un champ manquant — l'outil criait au loup à chaque exécution."""
    offres = [_offre(source_id="1", remote=False), _offre(source_id="2", remote=False)]
    resultat = diagnostiquer_source(FausseSource(ConnectorResult(offers=offres)), {})
    assert "remote" not in resultat["champs_facultatifs_vides"]
    assert verdict(resultat)[0] == "ok"


def test_zero_offre_sans_erreur_est_suspect():
    resultat = diagnostiquer_source(FausseSource(ConnectorResult()), {})
    etat, explication = verdict(resultat)
    assert etat == "suspect"
    assert "aucune offre" in explication


def test_source_non_configuree_nomme_les_cles_manquantes():
    source = FausseSource(ConnectorResult(errors=["Clé RAPIDAPI_KEY absente du .env"]), configure=False)
    etat, explication = verdict(diagnostiquer_source(source, {}))
    assert etat == "ko"
    assert "RAPIDAPI_KEY" in explication


def test_le_diagnostic_ne_leve_jamais():
    resultat = diagnostiquer_source(FausseSource(RuntimeError("boum")), {})
    assert verdict(resultat)[0] == "ko"
    assert "boum" in resultat["erreurs"][0]


def test_rapport_signale_une_description_vide():
    resultat = diagnostiquer_source(FausseSource(ConnectorResult(offers=[_offre(description="")])), {})
    texte = rapport_texte([resultat])
    assert "0 caractère(s)" in texte
    assert "l'IA et le score n'auront rien à lire" in texte


@pytest.mark.parametrize(
    "code, attendu",
    [(401, "clé"), (403, "accès refusé"), (429, "quota"), (503, "maintenance")],
)
def test_resume_erreur_est_une_phrase_francaise_sur_une_ligne(code, attendu):
    """str(httpx.HTTPStatusError) fait deux lignes et renvoie vers MDN en anglais ;
    ces messages sont affichés tels quels dans l'onglet Sources."""
    requete = httpx.Request("GET", "https://exemple.fr/offres")
    exc = httpx.HTTPStatusError("boum", request=requete, response=httpx.Response(code, request=requete))
    message = resume_erreur(exc)
    assert "\n" not in message
    assert "developer.mozilla.org" not in message
    assert attendu in message
    assert str(code) in message


def test_resume_erreur_sur_un_probleme_reseau():
    assert "connexion impossible" in resume_erreur(httpx.ConnectError("dns"))
    assert "délai dépassé" in resume_erreur(httpx.ReadTimeout("lent"))


def test_capture_des_reponses_brutes(tmp_path, monkeypatch):
    """La capture fige la réponse réelle : matière première des fixtures V1."""
    from app.connectors.base import Connector

    def transport_bidon(request):
        return httpx.Response(200, json={"offres": []}, request=request)

    connector = Connector()
    monkeypatch.setattr(
        connector, "client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(transport_bidon),
            event_hooks={"response": [_enregistrer_reponse]},
        ),
    )
    dossier = tmp_path / "diagnostic"
    with capture_reponses(dossier):
        with connector.client() as client:
            client.get("https://exemple.fr/api/offres")

    fichiers = sorted(f.name for f in dossier.iterdir())
    assert any(f.endswith(".json") for f in fichiers)
    assert any(f.endswith(".meta.txt") for f in fichiers)
    meta = next(f for f in dossier.iterdir() if f.name.endswith(".meta.txt")).read_text(encoding="utf-8")
    assert "HTTP 200" in meta and "exemple.fr" in meta


def test_le_nom_du_fichier_capture_garde_le_chemin_de_l_url(tmp_path, monkeypatch):
    """Régression : with_suffix() amputait « algolia.net-1-indexes » au dernier point,
    deux endpoints d'un même hôte se retrouvaient avec le même nom."""
    from app.connectors.base import Connector

    connector = Connector()
    monkeypatch.setattr(
        connector, "client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}, request=r)),
            event_hooks={"response": [_enregistrer_reponse]},
        ),
    )
    with capture_reponses(tmp_path):
        with connector.client() as client:
            client.get("https://dsn.algolia.net/1/indexes/queries")
            client.get("https://dsn.algolia.net/1/indexes/autres")

    noms = sorted(f.name for f in tmp_path.glob("*.json"))
    assert noms == [
        "00-dsn-algolia-net-1-indexes-queries.json",
        "01-dsn-algolia-net-1-indexes-autres.json",
    ]


def test_la_capture_est_desactivee_par_defaut(tmp_path):
    """Hors diagnostic, aucun scan ne doit écrire de réponse sur le disque."""
    from app.connectors import base

    assert base._dossier_capture is None
    with capture_reponses(tmp_path):
        assert base._dossier_capture == tmp_path
    assert base._dossier_capture is None


def test_la_capture_ne_fige_jamais_une_cle_dans_l_url(tmp_path, monkeypatch):
    """Adzuna passe app_id / app_key en paramètres d'URL, et la capture est faite
    pour être relue et partagée : les clés ne doivent pas s'y retrouver."""
    from app.connectors.base import Connector

    connector = Connector()
    monkeypatch.setattr(
        connector, "client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}, request=r)),
            event_hooks={"response": [_enregistrer_reponse]},
        ),
    )
    with capture_reponses(tmp_path):
        with connector.client() as client:
            client.get("https://api.adzuna.com/v1/search",
                       params={"app_id": "mon-id", "app_key": "ma-cle-secrete", "what": "QA"})

    meta = next(tmp_path.glob("*.meta.txt")).read_text(encoding="utf-8")
    assert "ma-cle-secrete" not in meta and "mon-id" not in meta
    assert "app_key=MASQUE" in meta
    assert "what=QA" in meta          # le reste de la requête reste lisible


def test_la_capture_masque_les_jetons_dans_le_corps(tmp_path, monkeypatch):
    """La réponse d'authentification France Travail contient un access_token."""
    from app.connectors.base import Connector

    connector = Connector()
    monkeypatch.setattr(
        connector, "client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(
                200, json={"access_token": "jeton-tres-secret", "expires_in": 1499}, request=r)),
            event_hooks={"response": [_enregistrer_reponse]},
        ),
    )
    with capture_reponses(tmp_path):
        with connector.client() as client:
            client.get("https://entreprise.francetravail.fr/connexion/oauth2/access_token")

    corps = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")
    assert "jeton-tres-secret" not in corps
    assert "MASQUE" in corps
    assert "1499" in corps            # le reste de la réponse est intact


def test_source_qui_repond_sans_rien_extraire_est_suspecte_pas_en_panne():
    """APEC et HelloWork signalent eux-mêmes « aucune offre extraite ». C'est le
    cas le plus sournois — il doit ressortir en SUSPECT, pas se noyer dans les KO."""
    from app.connectors.base import aucune_offre

    source = FausseSource(ConnectorResult(
        errors=[aucune_offre("la structure du site HelloWork a probablement changé.")]))
    etat, explication = verdict(diagnostiquer_source(source, {}))
    assert etat == "suspect"
    assert "HelloWork" in explication


def test_une_vraie_panne_reste_en_ko():
    source = FausseSource(ConnectorResult(errors=["Recherche : HTTP 403 — accès refusé par le site"]))
    assert verdict(diagnostiquer_source(source, {}))[0] == "ko"


def test_la_capture_range_chaque_source_dans_son_dossier(tmp_path, monkeypatch):
    """Six connecteurs qui déversent dans un dossier plat ne font pas des fixtures
    relisibles : chaque source a le sien."""
    import app.services.diagnostic as module
    from app.connectors.base import Connector

    class SourceQuiAppelle(Connector):
        def __init__(self, nom):
            self.name = nom
            self.label = nom

        def client(self):
            return httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}, request=r)),
                event_hooks={"response": [_enregistrer_reponse]},
            )

        def fetch(self, profile):
            with self.client() as client:
                client.get(f"https://exemple.fr/{self.name}")
            return ConnectorResult(offers=[_offre()])

    monkeypatch.setattr(module, "ALL_CONNECTORS", [SourceQuiAppelle("apec"), SourceQuiAppelle("wttj")])
    module.diagnostiquer({}, capture=tmp_path)

    assert sorted(d.name for d in tmp_path.iterdir()) == ["apec", "wttj"]
    assert list((tmp_path / "apec").glob("*.json"))
