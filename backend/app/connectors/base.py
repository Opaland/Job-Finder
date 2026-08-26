"""Socle commun des connecteurs de sites d'emploi.

Chaque connecteur renvoie une liste de RawOffer normalisées. Un connecteur qui
échoue (clé absente, site indisponible, format changé) ne bloque jamais le scan :
l'erreur est enregistrée dans les statistiques du scan.
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger("jobfinder.connecteurs")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


@dataclass
class RawOffer:
    source: str
    source_id: str
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    contract_type: str = ""
    salary_text: str = ""
    remote: bool = False
    published_at: datetime | None = None


@dataclass
class ConnectorResult:
    offers: list[RawOffer] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_published(value) -> datetime | None:
    """Date de publication ISO d'une API (suffixe Z accepté), ramenée en naïf.

    Les heures de l'application sont toutes naïves (voir models.local_now) : on
    retire le fuseau plutôt que de mélanger aware et naïf dans les comparaisons.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


# Requêtes par défaut, utilisées quand le profil n'en définit pas.
DEFAULT_QUERIES = ["test manager", "QA", "responsable test", "testeur", "quality assurance"]


def profile_queries(profile: dict) -> list[str]:
    """Requêtes de scan du profil, ou les défauts si rien n'est configuré."""
    queries = [q.strip() for q in (profile.get("search_queries") or []) if isinstance(q, str) and q.strip()]
    return queries or list(DEFAULT_QUERIES)


# Ce que veut dire un code HTTP, du point de vue de l'utilisateur.
EXPLICATIONS_HTTP = {
    401: "authentification refusée — si cette source utilise une clé, vérifie-la dans le .env",
    403: "accès refusé par le site (blocage anti-robot, ou domaine non autorisé par ton réseau)",
    404: "adresse introuvable — l'API de la source a probablement changé",
    429: "quota dépassé — trop de requêtes, réessaie plus tard",
    500: "le site est en panne", 502: "le site est en panne",
    503: "site en maintenance ou surchargé", 504: "le site n'a pas répondu à temps",
}


# Préfixe des messages « la source a répondu, mais je n'en tire rien ». Ce n'est
# pas une panne : c'est un format qui a changé, et c'est le cas le plus sournois
# (le scan se termine normalement). Le diagnostic s'appuie sur ce préfixe pour
# le distinguer d'un échec réseau — d'où une constante plutôt qu'une phrase libre.
AUCUNE_OFFRE = "Aucune offre extraite"


def aucune_offre(precision: str) -> str:
    return f"{AUCUNE_OFFRE} : {precision}"


def resume_erreur(exc: Exception) -> str:
    """Phrase française courte pour une erreur réseau d'un connecteur.

    `str(httpx.HTTPStatusError)` tient sur deux lignes et renvoie vers une page
    MDN en anglais : illisible dans l'onglet Sources, qui affiche ces messages
    tels quels. Tous les connecteurs passent par ici.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return f"HTTP {code} — {EXPLICATIONS_HTTP.get(code, 'réponse inattendue du site')}"
    if isinstance(exc, httpx.TimeoutException):
        return "délai dépassé — le site n'a pas répondu dans les temps"
    if isinstance(exc, httpx.TransportError):
        return "connexion impossible — réseau, DNS ou site injoignable"
    return str(exc).splitlines()[0][:200]


# Capture des réponses brutes : dossier cible, ou None (comportement normal).
# Tous les connecteurs passent par Connector.client() — un seul point d'accroche
# suffit donc à figer ce que les sources renvoient vraiment, sans les modifier.
_dossier_capture: Path | None = None


@contextmanager
def capture_reponses(dossier: Path):
    """Enregistre dans `dossier` chaque réponse HTTP reçue par les connecteurs.

    Sert à constituer des fixtures à partir de vraies réponses (validation V1) :
    les tests des connecteurs ne tournent aujourd'hui que sur des payloads écrits
    à la main d'après la documentation des API.

    C'est l'appelant qui nomme le dossier — un par exécution, sinon deux
    diagnostics successifs mélangeraient leurs captures.
    """
    global _dossier_capture
    dossier.mkdir(parents=True, exist_ok=True)
    precedent = _dossier_capture
    _dossier_capture = dossier
    try:
        yield dossier
    finally:
        _dossier_capture = precedent


# Une capture est faite pour être relue, jointe à un rapport de bug, partagée.
# Rien de secret ne doit y figurer : Adzuna passe ses clés dans l'URL et France
# Travail renvoie un jeton dans le corps de la réponse d'authentification.
PARAMS_SENSIBLES = frozenset({
    "app_id", "app_key", "api_key", "apikey", "key", "token", "access_token",
    "client_id", "client_secret", "secret", "password",
})
MASQUE = "MASQUE"

_CHAMPS_SECRETS = re.compile(
    r'("(?:access_token|refresh_token|id_token|api_key|client_secret)"\s*:\s*")[^"]*(")',
    re.IGNORECASE,
)


def _url_masquee(url: httpx.URL) -> str:
    """URL sans ses paramètres sensibles, pour le fichier descriptif."""
    base = f"{url.scheme}://{url.host}{url.path}"
    items = url.params.multi_items()
    if not items:
        return base
    query = "&".join(
        f"{cle}={MASQUE if cle.lower() in PARAMS_SENSIBLES else valeur}" for cle, valeur in items
    )
    return f"{base}?{query}"


def _corps_masque(reponse: httpx.Response) -> bytes:
    """Corps de réponse, jetons d'authentification masqués."""
    if "json" not in reponse.headers.get("content-type", ""):
        return reponse.content
    try:
        texte = reponse.content.decode("utf-8")
    except UnicodeDecodeError:
        return reponse.content
    masque, remplacements = _CHAMPS_SECRETS.subn(rf"\1{MASQUE}\2", texte)
    return masque.encode("utf-8") if remplacements else reponse.content


def _extension(reponse: httpx.Response) -> str:
    type_contenu = reponse.headers.get("content-type", "")
    if "json" in type_contenu:
        return "json"
    if "html" in type_contenu:
        return "html"
    return "txt"


def _enregistrer_reponse(reponse: httpx.Response) -> None:
    """Hook httpx : écrit la réponse sur le disque. N'échoue jamais le scan."""
    if _dossier_capture is None:
        return
    try:
        # Les hooks de réponse sont appelés avant la lecture du corps.
        reponse.read()
        url = reponse.request.url
        nom = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{url.host}{url.path}").strip("-")[:80]
        # Pas de with_suffix ici : « algolia.net-1-indexes » se ferait amputer
        # de tout ce qui suit le dernier point.
        rang = len(list(_dossier_capture.glob("*.meta.txt")))
        base = _dossier_capture / f"{rang:02d}-{nom}"
        base.with_name(f"{base.name}.{_extension(reponse)}").write_bytes(_corps_masque(reponse))
        base.with_name(f"{base.name}.meta.txt").write_text(
            f"{reponse.request.method} {_url_masquee(url)}\n"
            f"HTTP {reponse.status_code}\n"
            f"content-type: {reponse.headers.get('content-type', '')}\n"
            f"{len(reponse.content)} octets\n"
            f"(clés et jetons remplacés par « {MASQUE} » — capture destinée à être partagée)\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 — une capture ratée ne casse pas un scan
        logger.exception("Capture de la réponse brute impossible")


class Connector:
    """Interface d'un connecteur. `name` est l'identifiant technique, `label` le nom affiché."""

    name = "base"
    label = "Base"
    needs_key = False

    def is_configured(self) -> bool:
        return True

    def fetch(self, profile: dict) -> ConnectorResult:  # pragma: no cover - interface
        raise NotImplementedError

    def client(self) -> httpx.Client:
        # retries=2 : nouvelles tentatives sur les erreurs de CONNEXION uniquement
        # (jamais sur un 4xx/5xx reçu, pour ne pas aggraver un blocage anti-robot).
        transport = httpx.HTTPTransport(retries=2)
        return httpx.Client(
            headers=DEFAULT_HEADERS, timeout=30, follow_redirects=True, transport=transport,
            event_hooks={"response": [_enregistrer_reponse]},
        )


def dedupe_raw(offers: list[RawOffer]) -> list[RawOffer]:
    """Dédoublonne par (source, source_id) au sein d'un même connecteur."""
    seen: set[tuple[str, str]] = set()
    out = []
    for offer in offers:
        key = (offer.source, offer.source_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(offer)
    return out
