"""Mesure le temps des opérations coûteuses sur un volume réaliste d'offres.

Toutes les optimisations du projet (index mémoire du dédoublonnage, `load_only`
du digest, regex unique de `marche.py`) ont été écrites d'après des jeux de
données fabriqués. Cette commande donne des chiffres, sur une base jetable.

    python scripts/mesures.py            # 2000 offres
    python scripts/mesures.py 10000      # autre volume

Le seuil d'alerte est 1 seconde : au-delà, une page se sent dans l'interface.
"""
from __future__ import annotations

import random
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "backend"))

SEUIL_ALERTE = 1.0

ENTREPRISES = [
    "Éditeur santé", "ESN lyonnaise", "Cabinet de conseil", "Banque régionale",
    "Startup mobilité", "Groupe industriel", "Assurance", "Retail & e-commerce",
]
TITRES = [
    "Test Manager", "QA Lead", "Ingénieur de test", "Responsable qualité logicielle",
    "Testeur automaticien", "QA Engineer", "Chef de projet test", "Test Analyst",
]
VILLES = ["Lyon", "Villeurbanne", "Brignais", "Écully", "Paris", "Grenoble", "Télétravail"]
DESCRIPTION = (
    "Vous piloterez la stratégie de test d'une plateforme critique : rédaction du plan "
    "de test, animation d'une équipe QA, automatisation Selenium et Cypress, intégration "
    "continue Jenkins, suivi des anomalies sous Jira et Xray, reporting auprès du COPIL. "
    "Environnement Agile SAFe, API REST, bases PostgreSQL. Rémunération 55-65 k€ selon profil."
)


def _chrono(libelle: str, fonction):
    """Exécute, chronomètre, affiche. Renvoie (secondes, résultat)."""
    debut = time.perf_counter()
    resultat = fonction()
    duree = time.perf_counter() - debut
    alerte = "  ← au-delà du seuil" if duree > SEUIL_ALERTE else ""
    print(f"  {libelle:<44} {duree:7.3f} s{alerte}")
    return duree, resultat


def peupler(db, nombre: int) -> None:
    """Crée `nombre` offres plausibles, avec historiques et entretiens."""
    from app.models import STATUTS_ACTIFS, STATUTS_CLOS, STATUTS_NON_TRAITES, Offer, local_now
    from app.services.textutils import fingerprint

    # Répartition plausible d'une recherche en cours : beaucoup d'offres pas
    # encore traitées, quelques candidatures, quelques dossiers clos. Les statuts
    # viennent des groupes de models.py — jamais de liste littérale.
    tirage = (STATUTS_NON_TRAITES * 4) + (STATUTS_ACTIFS * 2) + STATUTS_CLOS

    alea = random.Random(42)          # reproductible d'une mesure à l'autre
    maintenant = local_now()
    for i in range(nombre):
        titre = f"{alea.choice(TITRES)} H/F"
        entreprise = alea.choice(ENTREPRISES)
        statut = alea.choice(tirage)
        historique = [{"status": "nouvelle", "date": maintenant.isoformat(), "par": "scan"}]
        if statut not in STATUTS_NON_TRAITES:
            historique.append({"status": "postulee", "date": maintenant.isoformat(), "par": "utilisateur"})
            historique.append({"status": statut, "date": maintenant.isoformat(), "par": "utilisateur"})
        db.add(Offer(
            fingerprint=fingerprint(f"{titre} {i}", entreprise),
            source=alea.choice(["france_travail", "adzuna", "jsearch", "wttj", "apec", "hellowork"]),
            source_id=str(i),
            title=titre, company=entreprise, location=alea.choice(VILLES),
            description=DESCRIPTION, url=f"https://exemple.fr/offre/{i}",
            contract_type=alea.choice(["CDI", "CDD", "Freelance"]),
            salary_text=f"{alea.randint(40, 75)}k€", remote=alea.random() < 0.3,
            status=statut, status_history=historique,
            score=float(alea.randint(20, 99)), final_score=float(alea.randint(20, 99)),
            collected_at=maintenant, last_seen_at=maintenant,
        ))
        if i % 500 == 0:
            db.flush()
    db.commit()


def mesurer(db, nombre: int) -> list[tuple[str, float]]:
    from app.services.digest import build_digest
    from app.services.marche import (
        competences_demandees, fraicheur, manques_recurrents, montants_annuels, qui_recrute,
    )
    from app.services.scan import index_offres_connues

    from app.models import Offer

    print(f"\nMesures sur {nombre} offres\n" + "-" * 62)
    resultats = []

    duree, _ = _chrono("Index de dédoublonnage (début de scan)",
                       lambda: index_offres_connues(db))
    resultats.append(("index de dédoublonnage", duree))

    duree, _ = _chrono("Construction du digest quotidien", lambda: build_digest(db))
    resultats.append(("digest", duree))

    duree, _ = _chrono("Marché : compétences demandées",
                       lambda: competences_demandees(db))
    resultats.append(("marché / compétences", duree))

    duree, _ = _chrono("Marché : manques par rapport au CV",
                       lambda: manques_recurrents(db))
    resultats.append(("marché / manques", duree))

    duree, _ = _chrono("Marché : qui recrute", lambda: qui_recrute(db))
    resultats.append(("marché / entreprises", duree))

    duree, _ = _chrono("Marché : fraîcheur des offres", lambda: fraicheur(db))
    resultats.append(("marché / fraîcheur", duree))

    duree, _ = _chrono("Analyse des salaires (toutes les offres)",
                       lambda: [montants_annuels(s) for (s,) in db.query(Offer.salary_text).all()])
    resultats.append(("salaires", duree))
    return resultats


def main():
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    nombre = int(arguments[0]) if arguments else 2000

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.services.seeding import ensure_profile

    with tempfile.TemporaryDirectory() as dossier:
        moteur = create_engine(f"sqlite:///{Path(dossier) / 'mesures.db'}")
        Base.metadata.create_all(moteur)
        db = sessionmaker(bind=moteur, autoflush=False, expire_on_commit=False)()
        try:
            # Profil issu du seed (CV, compétences) : sans lui, la mesure de
            # « manques par rapport au CV » comparerait à un profil vide.
            ensure_profile(db)
            db.commit()
            _chrono(f"Création de {nombre} offres de test", lambda: peupler(db, nombre))
            resultats = mesurer(db, nombre)
        finally:
            db.close()

    lentes = [(nom, duree) for nom, duree in resultats if duree > SEUIL_ALERTE]
    print("-" * 62)
    if lentes:
        print(f"{len(lentes)} opération(s) au-dessus de {SEUIL_ALERTE} s :")
        for nom, duree in lentes:
            print(f"  - {nom} : {duree:.3f} s")
        sys.exit(1)
    print(f"Tout est sous {SEUIL_ALERTE} s. Total : {sum(d for _, d in resultats):.3f} s.")


if __name__ == "__main__":
    main()
