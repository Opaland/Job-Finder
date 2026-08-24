"""Intégration IA via la session locale de Claude Code (CLI `claude`).

L'application n'utilise AUCUNE clé API : elle s'appuie sur la CLI Claude Code
installée sur le poste (abonnement local de l'utilisateur). Deux usages :

  1. Affiner le score des meilleures offres (avis qualitatif 0-100 + justification).
  2. Générer une lettre de motivation adaptée à une offre, à partir de la lettre
     type et du CV.

Si la CLI n'est pas trouvée (ou AI_MODE=off), l'application fonctionne
normalement avec le score par règles uniquement.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from ..config import settings


def cli_available() -> bool:
    if settings.ai_mode.lower() == "off":
        return False
    return shutil.which(settings.claude_cli) is not None


def _run_claude(prompt: str, timeout: int = 300) -> str | None:
    """Lance `claude -p` en local et renvoie le texte du résultat, ou None en cas d'échec."""
    exe = shutil.which(settings.claude_cli)
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        return data.get("result") or None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _extract_json(text: str) -> dict | None:
    """Extrait le premier objet JSON d'une réponse texte."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def ai_score_offer(offer: dict, cv_text: str) -> tuple[float, str] | None:
    """Demande à Claude un avis d'adéquation offre/CV. Renvoie (score, justification) ou None."""
    if not cli_available():
        return None
    prompt = f"""Tu es un expert du recrutement QA/test logiciel. Évalue l'adéquation entre ce CV et cette offre d'emploi.

CV (résumé) :
{cv_text[:6000]}

OFFRE :
Titre : {offer.get('title', '')}
Entreprise : {offer.get('company', '')}
Lieu : {offer.get('location', '')}
Contrat : {offer.get('contract_type', '')}
Description : {offer.get('description', '')[:6000]}

Réponds UNIQUEMENT avec un objet JSON de la forme :
{{"score": <0-100>, "raison": "<2 phrases max en français expliquant le score>"}}

Barème : 90-100 = poste identique à son métier actuel (Test Manager/QA Lead) et contexte idéal ;
70-89 = très bon fit ; 50-69 = fit correct avec des réserves ; 30-49 = éloigné ; 0-29 = hors cible."""
    result = _run_claude(prompt, timeout=240)
    if not result:
        return None
    data = _extract_json(result)
    if not data or "score" not in data:
        return None
    try:
        score = float(data["score"])
    except (TypeError, ValueError):
        return None
    reason = str(data.get("raison", ""))[:1000]
    return (max(0.0, min(100.0, score)), reason)


def ai_email(offer: dict, cv_text: str, kind: str) -> dict | None:
    """Génère un email de candidature ou de relance. Renvoie {"objet", "corps"} ou None."""
    if not cli_available():
        return None
    if kind == "relance":
        consigne = (
            "un EMAIL DE RELANCE courtois et bref (5 à 8 phrases) : rappelle la candidature "
            "envoyée pour ce poste, réaffirme l'intérêt avec UN argument fort tiré du CV, "
            "propose un échange téléphonique, sans jamais paraître insistant"
        )
    else:
        consigne = (
            "un EMAIL DE CANDIDATURE bref (6 à 10 phrases) accompagnant le CV et la lettre en "
            "pièces jointes : accroche personnalisée sur le poste, deux arguments forts tirés "
            "du CV (avec chiffres), disponibilité pour un entretien"
        )
    prompt = f"""Tu aides Cédric Moretti (Test Manager / QA Lead, 15 ans d'expérience, Lyon) à candidater.

Son CV (résumé) :
---
{cv_text[:5000]}
---

L'offre visée :
Titre : {offer.get('title', '')}
Entreprise : {offer.get('company', '')}
Description : {offer.get('description', '')[:4000]}

Rédige {consigne}. Ton professionnel et direct, en français, signé « Cédric Moretti ».

Réponds UNIQUEMENT avec un objet JSON de la forme :
{{"objet": "<objet de l'email>", "corps": "<corps de l'email avec sauts de ligne \\n>"}}"""
    result = _run_claude(prompt, timeout=240)
    if not result:
        return None
    data = _extract_json(result)
    if not data or "objet" not in data or "corps" not in data:
        return None
    return {"objet": str(data["objet"])[:200], "corps": str(data["corps"])}


def ai_interview_prep(offer: dict, cv_text: str) -> str | None:
    """Génère une fiche de préparation d'entretien pour l'offre. None si IA indisponible."""
    if not cli_available():
        return None
    prompt = f"""Tu prépares Cédric Moretti (Test Manager / QA Lead, 15 ans d'expérience, Lyon) à un
entretien d'embauche pour cette offre.

Son CV (résumé) :
---
{cv_text[:6000]}
---

L'offre :
Titre : {offer.get('title', '')}
Entreprise : {offer.get('company', '')}
Lieu : {offer.get('location', '')}
Description : {offer.get('description', '')[:6000]}

Rédige une fiche de préparation d'entretien en français, directe et actionnable, avec exactement
ces sections (titres en gras markdown) :

**Pitch d'accroche (30 secondes)** — un paragraphe à l'oral, personnalisé pour ce poste.
**Tes points forts face à cette annonce** — 4 à 6 puces reliant des éléments précis du CV aux attentes de l'offre (avec les chiffres du CV).
**Questions probables du recruteur** — 5 à 7 questions avec, pour chacune, l'angle de réponse conseillé en une phrase.
**Points de vigilance** — 2 à 4 aspects où le profil peut être challengé (surqualification, techno absente du CV…) et comment les retourner.
**Tes questions à poser** — 4 à 5 questions pertinentes qui montrent ta séniorité QA.

Réponds UNIQUEMENT avec la fiche, sans commentaire avant ou après."""
    return _run_claude(prompt, timeout=300)


def ai_cover_letter(offer: dict, cv_text: str, letter_template: str) -> str | None:
    """Génère une lettre de motivation adaptée à l'offre. Renvoie None si l'IA est indisponible."""
    if not cli_available():
        return None
    prompt = f"""Tu aides Cédric Moretti (Test Manager / QA Lead, 15 ans d'expérience, Lyon) à candidater.

Voici sa lettre de motivation type :
---
{letter_template[:8000]}
---

Voici son CV (résumé) :
---
{cv_text[:6000]}
---

Voici l'offre visée :
Titre : {offer.get('title', '')}
Entreprise : {offer.get('company', '')}
Lieu : {offer.get('location', '')}
Description : {offer.get('description', '')[:6000]}

Rédige la lettre de motivation ADAPTÉE à cette offre, en français, en gardant le ton et les
éléments forts de la lettre type, mais en la personnalisant pour l'entreprise et le poste
(reprends les mots-clés importants de l'offre, mets en avant les expériences du CV les plus
pertinentes pour CE poste). Longueur : 350 à 450 mots. Réponds UNIQUEMENT avec le texte de la
lettre, sans commentaire avant ou après."""
    return _run_claude(prompt, timeout=300)
