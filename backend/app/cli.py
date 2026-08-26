"""Commandes en ligne : scan et digest sans interface (pour le Planificateur de tâches Windows).

Usage :
    python -m app.cli scan       # scan complet + digest + email si configuré
    python -m app.cli digest     # (re)construit le digest du jour + email si configuré
    python -m app.cli sources    # diagnostic : ce que chaque source renvoie vraiment
    python -m app.cli sources --brut   # + fige les réponses brutes dans data/diagnostic/
"""
import sys
from pathlib import Path

from .config import DATA_DIR
from .database import SessionLocal, engine, ensure_schema
from .models import Profile, local_now
from .services.digest import build_digest, send_digest_email
from .services.scan import profile_to_dict, run_full_scan
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
