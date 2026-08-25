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
from ..models import STATUTS_CLOS, Offer, Profile, ScanRun, local_now
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


def find_twin(
    db: Session,
    title: str,
    company: str,
    *,
    fingerprints: dict[str, int] | None = None,
    company_index: dict[str, list[tuple[int, str]]] | None = None,
) -> Offer | None:
    """Offre déjà suivie correspondant à (titre, entreprise), ou None.

    Règle unique du dédoublonnage, partagée par le scan et l'ajout manuel :
    empreinte exacte d'abord, puis même entreprise + titre quasi identique.
    Sans entreprise identifiée, aucune fusion : deux « Test Manager H/F »
    d'entreprises inconnues peuvent être deux offres distinctes.

    `fingerprints` (empreinte → id) et `company_index` (entreprise normalisée →
    [(id, titre)]) sont fournis par le scan pour éviter une requête par offre.
    """
    company_key = normalize(company or "")
    if not company_key:
        return None
    fp = fingerprint(title, company)
    if fingerprints is not None:
        twin_id = fingerprints.get(fp)
        twin = db.get(Offer, twin_id) if twin_id else None
    else:
        twin = db.query(Offer).filter(Offer.fingerprint == fp).first()
    if twin is not None or len(company_key) < 3:
        return twin
    if company_index is not None:
        candidates = company_index.get(company_key, [])
    else:
        candidates = [
            (oid, otitle)
            for oid, otitle, ocompany in db.query(Offer.id, Offer.title, Offer.company).all()
            if normalize(ocompany or "") == company_key
        ]
    for oid, otitle in candidates:
        if titles_similar(title, otitle):
            return db.get(Offer, oid)
    return None


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

        # Index en mémoire des offres connues, construits en un seul parcours de
        # table : (source, source_id) → id, empreinte → id, et entreprise
        # normalisée → [(id, titre)] pour les doublons au titre légèrement
        # différent (« H/F », « CDI »…). Évite deux requêtes par offre rapportée.
        known_ids: dict[tuple[str, str], int] = {}
        fingerprints: dict[str, int] = {}
        company_index: dict[str, list[tuple[int, str]]] = {}
        for oid, osource, osource_id, ofp, otitle, ocompany in db.query(
            Offer.id, Offer.source, Offer.source_id, Offer.fingerprint, Offer.title, Offer.company
        ).all():
            known_ids[(osource, osource_id)] = oid
            fingerprints.setdefault(ofp, oid)
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
                existing_id = known_ids.get((raw.source, str(raw.source_id)))
                if existing_id:
                    existing = db.get(Offer, existing_id)
                    existing.last_seen_at = local_now()
                    existing.still_online = True
                    # On complète la description si la source en fournit une plus riche.
                    if len(raw.description or "") > len(existing.description or ""):
                        existing.description = raw.description
                    source_stat["seen"] += 1
                    continue

                twin = find_twin(
                    db, raw.title, raw.company,
                    fingerprints=fingerprints, company_index=company_index,
                )
                if twin:
                    # Même offre déjà connue via une autre source : on note la piste
                    # supplémentaire sans créer de doublon.
                    twin.last_seen_at = local_now()
                    twin.still_online = True
                    others = list(twin.other_sources or [])
                    entry = {"source": raw.source, "url": raw.url}
                    if entry not in others and raw.url != twin.url:
                        others.append(entry)
                        twin.other_sources = others
                    source_stat["seen"] += 1
                    continue

                offer = Offer(
                    fingerprint=fingerprint(raw.title, raw.company),
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
                    {"status": "nouvelle", "date": local_now().isoformat(), "par": "scan"}
                ]
                db.add(offer)
                db.flush()
                known_ids[(offer.source, offer.source_id)] = offer.id
                fingerprints.setdefault(offer.fingerprint, offer.id)
                new_key = normalize(offer.company or "")
                if len(new_key) >= 3:
                    company_index.setdefault(new_key, []).append((offer.id, offer.title))
                source_stat["new"] += 1

            db.commit()
            stats[connector.name] = source_stat

        # Marque hors-ligne les offres non revues depuis 15 jours (sans toucher au
        # statut) — uniquement pour les sources réellement scannées avec succès :
        # une offre manuelle ou d'une source désactivée/en panne ne peut pas être
        # « revue », elle ne doit donc pas être signalée « plus en ligne ».
        swept_sources = [
            name for name, s in stats.items()
            if not s.get("skipped") and (s.get("fetched", 0) > 0 or not s.get("errors"))
        ]
        if swept_sources:
            cutoff = local_now() - timedelta(days=15)
            db.query(Offer).filter(
                Offer.last_seen_at < cutoff,
                Offer.still_online.is_(True),
                Offer.source.in_(swept_sources),
            ).update({"still_online": False}, synchronize_session=False)
            db.commit()

        # Affinage IA (session locale Claude Code) des meilleures offres sans avis.
        # Pas de filtre sur la date de collecte : une offre enrichie (avis IA remis
        # à zéro) redevient candidate au prochain scan ; le volume reste borné par
        # ai_max_offers_per_scan, les mieux notées d'abord.
        ai_refined = 0
        if cli_available():
            candidates = (
                db.query(Offer)
                .filter(
                    Offer.ai_score.is_(None),
                    Offer.score >= settings.ai_min_rule_score,
                    Offer.status.notin_(STATUTS_CLOS),
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

        run.finished_at = local_now()
        run.status = "termine"
        run.source_stats = stats
        run.new_count = sum(s.get("new", 0) for s in stats.values())
        run.seen_count = sum(s.get("seen", 0) for s in stats.values())
        run.error_count = sum(len(s.get("errors", [])) for s in stats.values())
        if ai_refined:
            stats["_ia"] = {"label": "Affinage IA (Claude local)", "refined": ai_refined}
            run.source_stats = stats
        db.commit()

        from .journal import log_event

        log_event(db, "scan", f"Scan {trigger} terminé : {run.new_count} nouvelle(s) offre(s), "
                              f"{run.seen_count} déjà connue(s), {run.error_count} erreur(s) de source.")
        return run
    except Exception:
        run.finished_at = local_now()
        run.status = "erreur"
        db.commit()
        raise
    finally:
        _current_scan.update({"running": False})
        _scan_lock.release()


def run_full_scan(db: Session, trigger: str, send_email: bool):
    """Pipeline complet scan → digest → email éventuel.

    Point d'entrée unique du scan manuel (routeur), du scan quotidien
    (scheduler) et de la CLI : toute étape ajoutée ici profite aux trois.
    Renvoie (ScanRun, Digest, email_envoyé).
    """
    from .digest import build_digest, send_digest_email

    run = run_scan(db, trigger=trigger)
    digest = build_digest(db)
    sent = send_digest_email(db, digest) if send_email else False
    return run, digest, sent


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
