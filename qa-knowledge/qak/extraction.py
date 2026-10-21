"""Extraction du texte des documents (PDF, texte, Markdown) avec pages et sections.

Ce module ne connaît ni la base ni le catalogue : il transforme un fichier en
pages propres, en plan (titres de sections) et en passages prêts à indexer.
"""
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .textes import normaliser

# Toute modification de l'extraction, du découpage ou de la détection des métadonnées doit
# incrémenter ce numéro :
# l'actualisation réindexe alors les documents extraits par une version antérieure.
VERSION_EXTRACTEUR = 9

TAILLE_PASSAGE = 1400   # caractères visés par passage
PAGE_VIDE = 40          # moins de caractères utiles = page vide (scan, image)

RE_PAGE_IMPRIMEE = re.compile(r"\bpage\s+(\d{1,4})\s*(?:de|of|sur|/|von|z)\s*\d{1,4}\b", re.I)
RE_POINTILLES = re.compile(r"(?:\.\s?){5,}\s*\d*\s*$")
RE_TITRE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÀ-ÖØ-Þ«“\"(][^\n]{2,140})$")


@dataclass
class Page:
    numero: int                  # page physique du PDF (1 = première)
    imprimee: str | None         # numéro imprimé (« Page 12 de 80 »), s'il diffère
    texte: str
    sommaire: bool = False       # table des matières / index : exclue des recherches par défaut


@dataclass
class Titre:
    page: int
    ligne: int                   # index de ligne dans la page nettoyée (0 si inconnu)
    numero: str                  # « 4.2.1 » ou « » (titre non numéroté)
    titre: str


@dataclass
class Passage:
    page: int
    imprimee: str | None
    section_num: str
    section_titre: str
    texte: str
    sommaire: bool


@dataclass
class Extraction:
    pages: list[Page] = field(default_factory=list)
    plan: list[Titre] = field(default_factory=list)
    meta_pdf: dict = field(default_factory=dict)
    erreurs: list[str] = field(default_factory=list)
    plan_source: str = ""        # « signets » (outline PDF), « texte » (détection) ou « markdown »
    brut_debut: list[str] = field(default_factory=list)  # texte brut des premières pages (métadonnées)

    @property
    def nb_pages(self) -> int:
        return len(self.pages)

    def pages_vides(self) -> list[int]:
        return [p.numero for p in self.pages if not p.sommaire and len(p.texte.strip()) < PAGE_VIDE]

    def statut(self) -> tuple[str, str]:
        """(statut, explication) : ok, partiel, illisible ou echec."""
        if self.erreurs and not self.pages:
            return "echec", "; ".join(self.erreurs)
        if not self.pages:
            return "echec", "aucune page lisible"
        vides = self.pages_vides()
        texte = "".join(p.texte for p in self.pages)
        lettres = sum(c.isalpha() for c in texte)
        if len(vides) > 0.5 * len(self.pages):
            return "illisible", f"{len(vides)}/{len(self.pages)} pages sans texte (document scanné ? OCR nécessaire)"
        if texte and lettres / max(1, len(texte.replace(' ', '').replace('\n', ''))) < 0.6:
            return "illisible", "texte extrait majoritairement non alphabétique (encodage des polices ?)"
        if len(vides) > max(2, 0.1 * len(self.pages)):
            return "partiel", f"pages sans texte : {_plages(vides)}"
        if self.erreurs:
            return "partiel", "; ".join(self.erreurs)
        return "ok", f"{len(self.pages)} pages, plan {self.plan_source or 'absent'} ({len(self.plan)} titres)"


def _plages(nums: list[int]) -> str:
    out, debut, prec = [], None, None
    for n in nums + [None]:
        if debut is None:
            debut = prec = n
        elif n == prec + 1:
            prec = n
        else:
            out.append(f"{debut}" if debut == prec else f"{debut}-{prec}")
            debut = prec = n
    return ", ".join(out)


# ---------------------------------------------------------------- lecture brute

def _lire_pdf(chemin: Path) -> tuple[list[str], list[tuple[int, str, int]], dict, list[str]]:
    from pypdf import PdfReader  # import tardif : la recherche n'a pas besoin de pypdf

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    erreurs: list[str] = []
    lecteur = PdfReader(str(chemin))
    if lecteur.is_encrypted:
        try:
            lecteur.decrypt("")
        except Exception:
            return [], [], {}, ["PDF chiffré : extraction impossible"]
    textes = []
    for i, page in enumerate(lecteur.pages):
        try:
            textes.append(page.extract_text() or "")
        except Exception as exc:  # une page cassée ne doit pas perdre tout le document
            textes.append("")
            erreurs.append(f"page {i + 1} illisible ({type(exc).__name__})")
    signets = []
    try:
        def parcourir(noeuds, niveau=0):
            for n in noeuds:
                if isinstance(n, list):
                    parcourir(n, niveau + 1)
                else:
                    try:
                        signets.append((niveau, str(n.title).strip(), lecteur.get_destination_page_number(n) + 1))
                    except Exception:
                        pass
        parcourir(lecteur.outline)
    except Exception:
        erreurs.append("signets PDF illisibles (plan reconstruit depuis le texte)")
    meta = {}
    try:
        meta = {k.lstrip("/"): str(v) for k, v in (lecteur.metadata or {}).items()}
    except Exception:
        pass
    return textes, signets, meta, erreurs


def _lire_texte(chemin: Path) -> list[str]:
    brut = chemin.read_text(encoding="utf-8", errors="replace")
    # \f (saut de page) délimite les pages d'un texte issu de pdftotext ; sinon une seule « page ».
    return brut.split("\f") if "\f" in brut else [brut]


# ---------------------------------------------------------------- nettoyage

def _cle_ligne(ligne: str) -> str:
    return re.sub(r"\d+", "#", normaliser(ligne))


def _repetitions(pages: list[list[str]]) -> set[str]:
    """Lignes d'en-tête / pied de page : présentes sur au moins 40 % des pages."""
    if len(pages) < 4:
        return set()
    compte = Counter()
    for lignes in pages:
        compte.update({_cle_ligne(l) for l in lignes if l.strip()})
    seuil = max(3, 0.4 * len(pages))
    return {k for k, n in compte.items() if n >= seuil and k}


RE_ENTREE_INDEX = re.compile(r"\D[\s,]\d{1,3}(?:\s*[,-]\s*\d{1,3})*\s*$")


def _est_sommaire(lignes: list[str]) -> bool:
    """Table des matières (lignes à pointillés) ou index (« boundary value analysis 40, 41 »)."""
    utiles = [l for l in lignes if l.strip()]
    if sum(bool(RE_POINTILLES.search(l)) for l in utiles) >= 4:
        return True
    return len(utiles) >= 12 and sum(bool(RE_ENTREE_INDEX.search(l)) for l in utiles) >= 0.6 * len(utiles)


def _pages(textes: list[str]) -> list[Page]:
    brutes = [[l.rstrip() for l in t.replace("\r", "").split("\n")] for t in textes]
    repetees = _repetitions(brutes)
    pages = []
    for i, (texte, lignes) in enumerate(zip(textes, brutes), start=1):
        m = RE_PAGE_IMPRIMEE.search(texte)
        imprimee = m.group(1) if m and m.group(1) != str(i) else None
        utiles = [l for l in lignes if l.strip() and _cle_ligne(l) not in repetees]
        pages.append(Page(i, imprimee, "\n".join(utiles), _est_sommaire(lignes)))
    return pages


# ---------------------------------------------------------------- plan

def _numero(titre: str) -> tuple[str, str]:
    m = re.match(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(.*)$", titre)
    return (m.group(1), m.group(2).strip()) if m else ("", titre.strip())


def _successeur(courant: list[int], nouveau: list[int]) -> bool:
    """Un titre numéroté plausible suit le précédent : enfant (x.1), frère ou oncle (+1)."""
    if not courant:
        return len(nouveau) == 1 and nouveau[0] in (0, 1)
    if nouveau == courant + [1]:
        return True
    for k in range(1, len(courant) + 1):
        if len(nouveau) == k and nouveau[:k - 1] == courant[:k - 1] and nouveau[k - 1] == courant[k - 1] + 1:
            return True
    return False


def _plan_depuis_texte(pages: list[Page]) -> list[Titre]:
    """Repère les titres numérotés et garde la plus longue suite à numérotation cohérente.
    Cela écarte les listes numérotées (« 1. Aux bureaux nationaux… ») qui ressemblent
    à des titres : elles forment une suite courte qui casse celle des vrais chapitres."""
    candidats = []
    for p in pages:
        if p.sommaire:
            continue
        for i, ligne in enumerate(p.texte.split("\n")):
            l = ligne.strip()
            m = RE_TITRE.match(l)
            if m and not RE_POINTILLES.search(l) and not l.endswith((",", ";", ":")):
                num = [int(x) for x in m.group(1).split(".")]
                candidats.append((num, Titre(p.numero, i, m.group(1), m.group(2).strip())))
    # Les objectifs d'apprentissage en tête de chapitre répètent les titres (« 1.1 Principes… »)
    # quelques pages avant le vrai titre : une occurrence suivie, à moins de 8 pages, d'un titre
    # identique est écartée. Les répétitions lointaines restent : la chaîne la plus longue tranche.
    cles = [(t.numero, normaliser(t.titre)[:25]) for _, t in candidats]
    candidats = [c for i, c in enumerate(candidats)
                 if not any(cles[j] == cles[i] and candidats[j][1].page - c[1].page <= 8
                            for j in range(i + 1, len(candidats)))]
    # Plus longue chaîne où chaque titre « succède » au précédent (DP quadratique, n ≈ 300).
    n = len(candidats)
    meilleur, precedent = [0] * n, [-1] * n
    for j in range(n):
        if _successeur([], candidats[j][0]):
            meilleur[j] = 1
        for i in range(max(0, j - 400), j):
            # « >= » : à longueur égale, le prédécesseur le plus proche l'emporte (le vrai titre
            # « 1 Fundamentals » plutôt que l'item « 1. To national boards » du préambule).
            if meilleur[i] and meilleur[i] + 1 >= meilleur[j] and _successeur(candidats[i][0], candidats[j][0]):
                meilleur[j], precedent[j] = meilleur[i] + 1, i
    if not n or not max(meilleur):
        return []
    j, chaine = max(range(n), key=lambda k: meilleur[k]), []
    while j != -1:
        chaine.append(candidats[j][1])
        j = precedent[j]
    return chaine[::-1]


def _ligne_du_titre(lignes: list[str], num: str, libelle: str) -> int:
    """Ligne où commence le titre d'un signet : titre complet, titre coupé sur deux lignes,
    puis numéro seul en début de ligne. 0 (début de page) en dernier recours."""
    cle = normaliser(libelle)[:30]
    norm = [normaliser(l) for l in lignes]
    for i, l in enumerate(norm):
        if cle and cle in l:
            return i
    for i in range(len(norm) - 1):
        if cle and cle in f"{norm[i]} {norm[i + 1]}" and normaliser(libelle)[:8] in norm[i]:
            return i
    if num:
        for i, l in enumerate(lignes):
            if re.match(rf"\s*{re.escape(num)}\.?\s", l):
                return i
    return 0


def _plan_depuis_signets(signets, pages: list[Page]) -> list[Titre]:
    plan, dernier = [], ""
    for _niveau, titre, page in signets:
        if not (1 <= page <= len(pages)):
            continue
        num, libelle = _numero(titre)
        # Un signet non numéroté (« Mots-clés », intertitre) reste dans sa section parente.
        dernier = num = num or dernier
        ligne = _ligne_du_titre(pages[page - 1].texte.split("\n"), num, libelle)
        plan.append(Titre(page, ligne, num, libelle))
    plan.sort(key=lambda t: (t.page, t.ligne))
    return plan


def _plan_markdown(pages: list[Page]) -> list[Titre]:
    plan = []
    for p in pages:
        for i, l in enumerate(p.texte.split("\n")):
            m = re.match(r"^#{1,4}\s+(.+)$", l.strip())
            if m:
                num, libelle = _numero(m.group(1))
                plan.append(Titre(p.numero, i, num, libelle))
    return plan


# ---------------------------------------------------------------- point d'entrée

def extraire(chemin: Path) -> Extraction:
    chemin = Path(chemin)
    ext = Extraction()
    try:
        if chemin.suffix.lower() == ".pdf":
            textes, signets, ext.meta_pdf, ext.erreurs = _lire_pdf(chemin)
        elif chemin.suffix.lower() in (".txt", ".md", ".markdown"):
            textes, signets = _lire_texte(chemin), []
        else:
            ext.erreurs.append(f"format non pris en charge : {chemin.suffix or 'sans extension'} (PDF, .txt ou .md)")
            return ext
    except Exception as exc:
        ext.erreurs.append(f"lecture impossible ({type(exc).__name__} : {str(exc)[:120]})")
        return ext
    ext.pages = _pages(textes)
    ext.brut_debut = textes[:6]
    if chemin.suffix.lower() in (".md", ".markdown"):
        ext.plan, ext.plan_source = _plan_markdown(ext.pages), "markdown"
    else:
        # Les signets ne sont retenus que s'ils portent une vraie numérotation de sections.
        plan_signets = _plan_depuis_signets(signets, ext.pages) if signets else []
        if sum(bool(t.numero) for t in plan_signets) >= 3:
            ext.plan, ext.plan_source = plan_signets, "signets"
        else:
            ext.plan = _plan_depuis_texte(ext.pages)
            ext.plan_source = "texte" if ext.plan else ""
    return ext


def _couper(texte: str, taille: int = TAILLE_PASSAGE) -> list[str]:
    """Coupe aux fins de paragraphe / de phrase pour rester lisible."""
    if len(texte) <= taille * 1.3:
        return [texte]
    morceaux, courant = [], ""
    for ligne in texte.split("\n"):
        if len(courant) + len(ligne) > taille and len(courant) > taille * 0.5:
            morceaux.append(courant.strip())
            courant = ""
        courant += ligne + "\n"
    if courant.strip():
        if morceaux and len(courant) < taille * 0.3:
            morceaux[-1] += "\n" + courant.strip()
        else:
            morceaux.append(courant.strip())
    return morceaux


def passages(ext: Extraction) -> list[Passage]:
    """Découpe les pages en passages rattachés à leur section. Un passage ne franchit
    jamais une page : chaque citation garde un numéro de page exact."""
    par_page: dict[int, list[Titre]] = {}
    for t in ext.plan:
        par_page.setdefault(t.page, []).append(t)
    section = Titre(0, 0, "", "")
    out = []
    for p in ext.pages:
        lignes = p.texte.split("\n")
        coupures = sorted(par_page.get(p.numero, []), key=lambda t: t.ligne)
        bornes = [0] + [t.ligne for t in coupures] + [len(lignes)]
        sections = [section] + coupures
        for (debut, fin), sec in zip(zip(bornes, bornes[1:]), sections):
            bloc = "\n".join(lignes[debut:fin]).strip()
            for morceau in _couper(bloc) if bloc else []:
                if len(morceau) >= 20:
                    out.append(Passage(p.numero, p.imprimee, sec.numero, sec.titre, morceau, p.sommaire))
        if coupures:
            section = coupures[-1]
    return out
