"""Test de mutation : que valent vraiment les tests de Job Finder ?

Une suite verte ne prouve rien par elle-même. Le test de mutation pose la seule
question qui compte : **si j'abîme le code, les tests s'en aperçoivent-ils ?**

On introduit une par une des fautes plausibles (un `<` qui devient `<=`, un
`and` qui devient `or`, un seuil décalé de 1, une condition inversée) et on
relance la suite :

  - la suite échoue  → la mutation est **tuée**, les tests font leur travail ;
  - la suite passe   → la mutation **survit**, personne ne garde ce bout de code.

Chaque survivant est un trou : une ligne qu'on pourrait casser en production
sans que rien ne le signale.

    python scripts/mutation.py                    # les modules critiques
    python scripts/mutation.py scoring textutils  # ciblé
    python scripts/mutation.py --liste            # modules disponibles

Sécurité : le dépôt n'est JAMAIS modifié. Le script travaille sur une copie
jetable de ton arbre de travail (fichiers suivis + non ignorés) dans un dossier
temporaire, supprimée à la fin — même en cas d'interruption.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Modules dont une régression coûterait le plus cher, avec les tests qui les
# couvrent. Cibler les tests garde le temps de réponse raisonnable : la suite
# complète est rejouée pour chaque mutation.
CIBLES = {
    "scoring": ("app/services/scoring.py", ["tests/test_scoring.py"]),
    "textutils": ("app/services/textutils.py", ["tests/test_similarity.py", "tests/test_scoring.py"]),
    "scan": ("app/services/scan.py", ["tests/test_scan_dedupe.py", "tests/test_queries.py"]),
    "digest": ("app/services/digest.py", ["tests/test_digest_enrich.py", "tests/test_rappels.py"]),
    "diagnostic": ("app/services/diagnostic.py", ["tests/test_diagnostic.py"]),
    "justificatif": ("app/services/justificatif.py", ["tests/test_justificatif.py"]),
    "marche": ("app/services/marche.py", ["tests/test_marche.py"]),
    "verrou": ("app/services/verrou.py", ["tests/test_verrou.py"]),
}


@dataclass
class Mutation:
    ligne: int
    avant: str
    apres: str
    description: str


# --- Les fautes qu'on simule -------------------------------------------------

INVERSES_COMPARAISON = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}

NOMS_COMPARAISON = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
    ast.Eq: "==", ast.NotEq: "!=", ast.In: "in", ast.NotIn: "not in",
    ast.Is: "is", ast.IsNot: "is not",
}


class Recenseur(ast.NodeVisitor):
    """Repère les endroits mutables, sans rien modifier."""

    def __init__(self):
        self.cibles: list[tuple[str, ast.AST, object]] = []

    def visit_Compare(self, noeud):
        for index, operateur in enumerate(noeud.ops):
            remplacant = INVERSES_COMPARAISON.get(type(operateur))
            if remplacant:
                self.cibles.append(("comparaison", noeud, (index, remplacant)))
        self.generic_visit(noeud)

    def visit_BoolOp(self, noeud):
        self.cibles.append(("booleen", noeud, None))
        self.generic_visit(noeud)

    def visit_Constant(self, noeud):
        valeur = noeud.value
        if isinstance(valeur, bool):
            self.cibles.append(("booleen_constant", noeud, None))
        elif isinstance(valeur, int) and not isinstance(valeur, bool):
            self.cibles.append(("entier", noeud, None))
        elif isinstance(valeur, float):
            self.cibles.append(("flottant", noeud, None))
        self.generic_visit(noeud)


class Muteur(ast.NodeTransformer):
    """Applique UNE mutation, celle qui porte sur `noeud_cible`."""

    def __init__(self, genre: str, noeud_cible, extra):
        self.genre, self.noeud_cible, self.extra = genre, noeud_cible, extra
        self.description = ""

    def visit_Compare(self, noeud):
        self.generic_visit(noeud)
        if self.genre == "comparaison" and noeud is self.noeud_cible:
            index, remplacant = self.extra
            ancien = type(noeud.ops[index])
            self.description = f"{NOMS_COMPARAISON[ancien]} → {NOMS_COMPARAISON[remplacant]}"
            noeud.ops[index] = remplacant()
        return noeud

    def visit_BoolOp(self, noeud):
        self.generic_visit(noeud)
        if self.genre == "booleen" and noeud is self.noeud_cible:
            if isinstance(noeud.op, ast.And):
                self.description, noeud.op = "and → or", ast.Or()
            else:
                self.description, noeud.op = "or → and", ast.And()
        return noeud

    def visit_Constant(self, noeud):
        if noeud is not self.noeud_cible:
            return noeud
        if self.genre == "booleen_constant":
            self.description = f"{noeud.value} → {not noeud.value}"
            return ast.copy_location(ast.Constant(value=not noeud.value), noeud)
        if self.genre in ("entier", "flottant"):
            nouvelle = noeud.value + 1
            self.description = f"{noeud.value} → {nouvelle}"
            return ast.copy_location(ast.Constant(value=nouvelle), noeud)
        return noeud


def mutations_possibles(source: str) -> list[tuple[str, str, Mutation]]:
    """Renvoie [(source mutée, genre, description)] pour un fichier."""
    arbre = ast.parse(source)
    recenseur = Recenseur()
    recenseur.visit(arbre)

    resultats = []
    for genre, noeud, extra in recenseur.cibles:
        arbre_neuf = ast.parse(source)
        # Retrouver le noeud équivalent dans l'arbre fraîchement reparsé :
        # même position, même type.
        jumeau = _retrouver(arbre_neuf, noeud)
        if jumeau is None:
            continue
        muteur = Muteur(genre, jumeau, extra)
        mute = muteur.visit(arbre_neuf)
        if not muteur.description:
            continue
        ast.fix_missing_locations(mute)
        resultats.append((
            ast.unparse(mute), genre,
            Mutation(getattr(noeud, "lineno", 0), "", "", muteur.description),
        ))
    return resultats


def _retrouver(arbre, modele):
    """Le noeud de `arbre` qui occupe la même position que `modele`."""
    for noeud in ast.walk(arbre):
        if (type(noeud) is type(modele)
                and getattr(noeud, "lineno", None) == getattr(modele, "lineno", None)
                and getattr(noeud, "col_offset", None) == getattr(modele, "col_offset", None)):
            return noeud
    return None


def _tests_verts(dossier: Path, tests: list[str]) -> bool:
    """True si la suite ciblée passe. `-x` : on s'arrête au premier échec."""
    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=dossier, capture_output=True, text=True, timeout=600,
    )
    return resultat.returncode == 0


def muter_un_module(copie: Path, cle: str, chemin_relatif: str, tests: list[str]) -> dict:
    fichier = copie / "backend" / chemin_relatif
    original = fichier.read_text(encoding="utf-8")
    candidats = mutations_possibles(original)

    print(f"\n{cle} — {len(candidats)} mutation(s) à éprouver "
          f"(tests : {', '.join(t.split('/')[-1] for t in tests)})")

    survivants, tuees, invalides = [], 0, 0
    try:
        for numero, (source_mutee, genre, mutation) in enumerate(candidats, 1):
            fichier.write_text(source_mutee, encoding="utf-8")
            try:
                verts = _tests_verts(copie / "backend", tests)
            except subprocess.TimeoutExpired:
                invalides += 1
                continue
            if verts:
                survivants.append((mutation.ligne, genre, mutation.description))
                marque = "SURVIT"
            else:
                tuees += 1
                marque = "tuée"
            print(f"  [{numero:3}/{len(candidats)}] ligne {mutation.ligne:4} "
                  f"{mutation.description:<24} {marque}")
    finally:
        fichier.write_text(original, encoding="utf-8")

    total = tuees + len(survivants)
    score = round(100 * tuees / total) if total else 100
    return {"module": chemin_relatif, "tuees": tuees, "survivants": survivants,
            "score": score, "invalides": invalides}


def _copier_arbre_de_travail(destination: Path) -> None:
    """Copie les fichiers suivis par git + les nouveaux non ignorés."""
    liste = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=RACINE, capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    for relatif in filter(None, liste):
        source = RACINE / relatif
        if not source.is_file():
            continue
        cible = destination / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, cible)


def main():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("modules", nargs="*", help="modules à éprouver (défaut : tous)")
    analyseur.add_argument("--liste", action="store_true", help="liste les modules disponibles")
    options = analyseur.parse_args()

    if options.liste:
        for cle, (chemin, tests) in CIBLES.items():
            print(f"  {cle:<14} {chemin:<34} {' '.join(tests)}")
        return

    inconnus = [m for m in options.modules if m not in CIBLES]
    if inconnus:
        print(f"Module(s) inconnu(s) : {', '.join(inconnus)}. "
              f"Disponibles : {', '.join(CIBLES)}.")
        sys.exit(1)
    choisis = options.modules or list(CIBLES)

    debut = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="mutation-jobfinder-") as temporaire:
        copie = Path(temporaire)
        # Copie jetable de l'ARBRE DE TRAVAIL — pas de HEAD : on veut éprouver le
        # code et les tests tels qu'ils sont maintenant, avant de committer.
        # Le vrai dépôt ne peut pas être abîmé, même si le script est interrompu.
        _copier_arbre_de_travail(copie)

        rapports = [muter_un_module(copie, cle, *CIBLES[cle]) for cle in choisis]

    print("\n" + "=" * 66)
    print("Score de mutation — part des fautes que les tests attrapent")
    print("=" * 66)
    for rapport in rapports:
        total = rapport["tuees"] + len(rapport["survivants"])
        print(f"  {rapport['module']:<36} {rapport['score']:3} %  "
              f"({rapport['tuees']}/{total} tuées)")

    tous_survivants = [(r["module"], *s) for r in rapports for s in r["survivants"]]
    if tous_survivants:
        print(f"\n{len(tous_survivants)} mutation(s) survivante(s) — autant de lignes que")
        print("l'on pourrait casser sans que la suite ne bronche :\n")
        for module, ligne, genre, description in tous_survivants:
            print(f"  {module}:{ligne}  {description}   ({genre})")
    else:
        print("\nAucune survivante : sur ce périmètre, la suite attrape tout.")

    print(f"\nDurée : {time.perf_counter() - debut:.0f} s.")
    if tous_survivants:
        sys.exit(1)


if __name__ == "__main__":
    main()
