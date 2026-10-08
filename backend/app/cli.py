"""Commandes en ligne : scan et digest sans interface (pour le Planificateur de tâches Windows).

Usage :
    python -m app.cli scan       # scan complet + digest + email si configuré
    python -m app.cli digest     # (re)construit le digest du jour + email si configuré
    python -m app.cli sources    # diagnostic : ce que chaque source renvoie vraiment
    python -m app.cli sources --brut   # + fige les réponses brutes dans data/diagnostic/
"""
import sys
from datetime import timedelta
from pathlib import Path

from .config import DATA_DIR
from .database import SessionLocal, engine, ensure_schema_avec_verrou
from .models import Profile, ScanRun, local_now
from .services.digest import build_digest, send_digest_email
from .services.emailer import smtp_configured
from .services.scan import profile_to_dict, run_full_scan
from .services.seeding import ensure_profile

# Un scan ignoré parce qu'un autre processus tient déjà le verrou est normal
# (chevauchement bref entre l'interface et la tâche planifiée) — mais si AUCUN
# scan n'a réussi depuis plus longtemps que ça, le verrou est probablement
# resté bloqué (processus planté sans libérer le fichier) et ça doit se voir.
VERROU_BLOQUE_DEPUIS = timedelta(hours=36)


def _signaler_scan_ignore(db, exc: Exception) -> None:
    dernier = (
        db.query(ScanRun)
        .filter(ScanRun.status == "termine")
        .order_by(ScanRun.finished_at.desc())
        .first()
    )
    silence = local_now() - dernier.finished_at if dernier else None
    if silence is None or silence > VERROU_BLOQUE_DEPUIS:
        depuis = "aucun scan n'a jamais réussi" if dernier is None else (
            f"le dernier scan réussi date du {dernier.finished_at:%d/%m/%Y %H:%M}"
        )
        print(
            f"ERREUR : scan ignoré ({exc}) et {depuis} — le verrou de scan "
            "(data/scan.lock) est probablement resté bloqué par un processus "
            "planté plutôt que par un scan en cours légitime.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Scan ignoré : {exc}")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "scan"
    ensure_schema_avec_verrou(engine)
    db = SessionLocal()
    try:
        ensure_profile(db)
        if command == "scan":
            try:
                run, digest, sent = run_full_scan(db, trigger="quotidien", send_email=True)
            except RuntimeError as exc:
                _signaler_scan_ignore(db, exc)
                return
            print(f"Scan terminé : {run.new_count} nouvelle(s) offre(s), {run.error_count} erreur(s).")
            print(f"Digest du {digest.date} construit (email envoyé : {sent}).")
            if smtp_configured() and not sent:
                print(
                    "ERREUR : l'email du digest n'a pas pu être envoyé alors que le SMTP "
                    "est configuré — voir les logs pour la cause exacte.",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif command == "sources":
            from .services.diagnostic import diagnostiquer, rapport_texte

            profil = profile_to_dict(db.get(Profile, 1))
            # Un dossier horodaté par exécution : deux diagnostics successifs ne
            # mélangent pas leurs captures.
            dossier = (
                Path(DATA_DIR) / "diagnostic" / local_now().strftime("%Y-%m-%d_%H%M%S")
                if "--brut" in sys.argv else None
            )
            print("Diagnostic des sources — interrogation en cours…\n")
            print(rapport_texte(diagnostiquer(profil, capture=dossier)))
            if dossier:
                print(f"\nRéponses brutes enregistrées dans {dossier}")
        elif command == "digest":
            digest = build_digest(db)
            sent = send_digest_email(db, digest)
            print(f"Digest du {digest.date} construit (email envoyé : {sent}).")
        else:
            print(__doc__)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
