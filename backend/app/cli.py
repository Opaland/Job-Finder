"""Commandes en ligne : scan et digest sans interface (pour le Planificateur de tâches Windows).

Usage :
    python -m app.cli scan     # scan complet + digest + email si configuré
    python -m app.cli digest   # (re)construit le digest du jour + email si configuré
"""
import sys

from .database import SessionLocal, engine, ensure_schema
from .services.digest import build_digest, send_digest_email
from .services.scan import run_full_scan
from .services.seeding import ensure_profile


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "scan"
    ensure_schema(engine)
    db = SessionLocal()
    try:
        ensure_profile(db)
        if command == "scan":
            try:
                run, digest, sent = run_full_scan(db, trigger="quotidien", send_email=True)
            except RuntimeError as exc:
                # L'application est ouverte et scanne déjà : rien à faire, et
                # surtout pas d'échec de tâche planifiée pour si peu.
                print(f"Scan ignoré : {exc}")
                return
            print(f"Scan terminé : {run.new_count} nouvelle(s) offre(s), {run.error_count} erreur(s).")
            print(f"Digest du {digest.date} construit (email envoyé : {sent}).")
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
