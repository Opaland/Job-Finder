"""Orchestration d'un scan : interroger les sources, dédoublonner, scorer, enregistrer.

Règle absolue : un scan n'archive et ne supprime JAMAIS une offre. Une offre qui
n'apparaît plus à la source est marquée `still_online=False`, mais elle reste
visible et son statut n'est modifié que par l'utilisateur.
"""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..connectors import ALL_CONNECTORS
from ..models import Offer, Profile, ScanRun, utcnow
from .claude_ai import ai_score_offer, cli_available
from .scoring import combined_score, score_offer
from .textutils import fingerprint, normalize, titles_similar

logger = logging.getLogger("jobfinder.scan")

# Un seul scan à la fois.
_scan_lock = threading.Lock()
_current_scan: dict = {"running": False, "scan_id": None}


def scan_status() -> dict:
    return dict(_current_scan)


def profile_to_dict(profile: Profile) -> dict:
    return {
        "target_titles": profile.target_titles or [],
        "skills": profile.skills or [],
        "location_keywords": profile.location_keywords or [],
        "radius_km": profile.radius_km,
        "remote_ok": profile.remote_ok,
        "contracts": profile.contracts or [],
        "sector_bonus": profile.sector_bonus or [],
        "excluded_keywords": profile.excluded_keywords or [],
        "scoring_weights": profile.scoring_weights or {},
        "search_queries": profile.search_queries or [],
    }


def offer_to_scoring_dict(offer: Offer) -> dict:
    return {
        "title": offer.title,
        "company": offer.company,
        "location": offer.location,
        "description": offer.description,
        "contract_type": offer.contract_type,
        "remote": offer.remote,
    }


def rescore_offer(offer: Offer, profile_dict: dict) -> None:
    """Recalcule score, détail et score final d'une offre (l'avis IA existant est conservé)."""
    result = score_offer(offer_to_scoring_dict(offer), profile_dict)
    offer.score = result.score
    offer.score_breakdown = result.breakdown
    offer.final_score = combined_score(offer.score, offer.ai_score)


def run_scan(db: Session, trigger: str = "manuel") -> ScanRun:
    """Exécute un scan complet. Bloquant — à lancer dans un thread/background task."""
    if not _scan_lock.acquire(blocking=False):
        raise RuntimeError("Un scan est déjà en cours")

    run = ScanRun(trigger=trigger, status="en_cours")
    db.add(run)
    db.commit()
    _current_scan.update({"running": True, "scan_id": run.id})

    try:
        profile = db.get(Profile, 1)
        profile_dict = profile_to_dict(profile)
        enabled = profile.sources_enabled or {}
        stats: dict[str, dict] = {}
        scan_started = utcnow()

        # Index (entreprise normalisée → offres connues) pour détecter les
        # doublons dont le titre varie légèrement (« H/F », « CDI »…).
        company_index: dict[str, list[tuple[int, str]]] = {}
        for oid, otitle, ocompany in db.query(Offer.id, Offer.title, Offer.company).all():
            key = normalize(ocompany or "")
            if len(key) >= 3:
                company_index.setdefault(key, []).append((oid, otitle))

        for connector in ALL_CONNECTORS:
            if not enabled.get(connector.name, True):
                stats[connector.name] = {"label": connector.label, "skipped": True}
                continue
            logger.info("Scan de %s…", connector.label)
            source_stat = {
                "label": connector.label,
                "fetched": 0, "new": 0, "seen": 0, "errors": [],
                "configured": connector.is_configured(),
            }
            try:
                result = connector.fetch(profile_dict)
            except Exception as exc:  # noqa: BLE001 — un connecteur ne doit jamais tuer le scan
                logger.exception("Connecteur %s en erreur", connector.name)
                source_stat["errors"].append(str(exc))
                stats[connector.name] = source_stat
                continue

            source_stat["errors"].extend(result.errors)
            source_stat["fetched"] = len(result.offers)

            for raw in result.offers:
                if not raw.title or not raw.source_id:
                    continue
                existing = (
                    db.query(Offer)
                    .filter(Offer.source == raw.source, Offer.source_id == str(raw.source_id))
                    .one_or_none()
                )
                if existing:
                    existing.last_seen_at = utcnow()
                    existing.still_online = True
                    # On complète la description si la source en fournit une plus riche.
                    if len(raw.description or "") > len(existing.description or ""):
                        existing.description = raw.description
                    source_stat["seen"] += 1
                    continue

                fp = fingerprint(raw.title, raw.company)
                twin = db.query(Offer).filter(Offer.fingerprint == fp).first()
                if twin is None:
                    # Même entreprise + titre quasi identique = même offre.
                    company_key = normalize(raw.company or "")
                    if len(company_key) >= 3:
                        for oid, otitle in company_index.get(company_key, []):
                            if titles_similar(raw.title, otitle):
                                twin = db.get(Offer, oid)
                                break
                if twin:
                    # Même offre déjà connue via une autre source : on note la piste
                    # supplémentaire sans créer de doublon.
                    twin.last_seen_at = utcnow()
                    twin.still_online = True
                    others = list(twin.other_sources or [])
                    entry = {"source": raw.source, "url": raw.url}
                    if entry not in others and raw.url != twin.url:
                        others.append(entry)
                        twin.other_sources = others
                    source_stat["seen"] += 1
                    continue

                offer = Offer(
                    fingerprint=fp,
                    source=raw.source,
                    source_id=str(raw.source_id),
                    title=raw.title[:300],
                    company=(raw.company or "")[:200],
                    location=(raw.location or "")[:200],
                    description=raw.description or "",
                    url=raw.url or "",
                    contract_type=(raw.contract_type or "")[:60],
                    salary_text=(raw.salary_text or "")[:200],
                    remote=bool(raw.remote),
                    published_at=raw.published_at,
                )
                rescore_offer(offer, profile_dict)
                offer.status_history = [
                    {"status": "nouvelle", "date": utcnow().isoformat(), "par": "scan"}
                ]
                db.add(offer)
                db.flush()
                new_key = normalize(offer.company or "")
                if len(new_key) >= 3:
                    company_index.setdefault(new_key, []).append((offer.id, offer.title))
                source_stat["new"] += 1

            db.commit()
            stats[connector.name] = source_stat

        # Marque hors-ligne les offres non revues depuis 15 jours (sans toucher au statut).
        cutoff = utcnow() - timedelta(days=15)
        db.query(Offer).filter(Offer.last_seen_at < cutoff, Offer.still_online.is_(True)).update(
            {"still_online": False}, synchronize_session=False
        )
        db.commit()

        # Affinage IA (session locale Claude Code) des meilleures nouvelles offres.
        ai_refined = 0
        if cli_available():
            candidates = (
                db.query(Offer)
                .filter(
                    Offer.collected_at >= scan_started,
                    Offer.ai_score.is_(None),
                    Offer.score >= settings.ai_min_rule_score,
                )
                .order_by(Offer.score.desc())
                .limit(settings.ai_max_offers_per_scan)
                .all()
            )
            profile_row = db.get(Profile, 1)
            for offer in candidates:
                verdict = ai_score_offer(offer_to_scoring_dict(offer), profile_row.cv_text)
                if verdict is None:
                    break  # CLI indisponible ou en échec : on n'insiste pas.
                offer.ai_score, offer.ai_reason = verdict
                offer.final_score = combined_score(offer.score, offer.ai_score)
                ai_refined += 1
            db.commit()

        run.finished_at = utcnow()
        run.status = "termine"
        run.source_stats = stats
        run.new_count = sum(s.get("new", 0) for s in stats.values())
        run.seen_count = sum(s.get("seen", 0) for s in stats.values())
        run.error_count = sum(len(s.get("errors", [])) for s in stats.values())
        from .journal import log_event

        log_event(db, "scan", f"Scan {trigger} terminé : {run.new_count} nouvelle(s) offre(s), "
                              f"{run.seen_count} déjà connue(s), {run.error_count} erreur(s) de source.")
        if ai_refined:
            stats["_ia"] = {"label": "Affinage IA (Claude local)", "refined": ai_refined}
            run.source_stats = stats
        db.commit()
        return run
    except Exception:
        run.finished_at = utcnow()
        run.status = "erreur"
        db.commit()
        raise
    finally:
        _current_scan.update({"running": False})
        _scan_lock.release()


def rescore_all(db: Session) -> int:
    """Recalcule le score règles de toutes les offres (après modification du profil)."""
    profile = db.get(Profile, 1)
    profile_dict = profile_to_dict(profile)
    count = 0
    for offer in db.query(Offer).all():
        rescore_offer(offer, profile_dict)
        count += 1
    db.commit()
    return count
