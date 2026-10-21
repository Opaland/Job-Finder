"""Bibliothèque documentaire : import, métadonnées, doublons, versions et index plein texte.

Deux fichiers :
- `bibliotheque/manifeste.json` (versionné) : une entrée par fichier source, indexée par
  empreinte SHA-256, avec les métadonnées détectées ou saisies. C'est la mémoire durable
  de la bibliothèque : il permet de reconstruire l'index à l'identique.
- `bibliotheque/index.db` (non versionné, reconstructible) : documents, sections et
  passages + table FTS5. `actualiser()` le remet à jour de façon incrémentale.
"""
import hashlib
from functools import cmp_to_key
import json
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import chemins, extraction
from .textes import normaliser, sans_accents

EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
IGNORES = {"lisezmoi.md", "readme.md"}  # notes du dossier sources, pas des documents

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, fichier TEXT NOT NULL,
    titre TEXT, code TEXT, type TEXT, niveau TEXT, domaine TEXT, version TEXT, langue TEXT,
    date_publication TEXT, source_officielle TEXT, page_officielle TEXT,
    statut_version TEXT DEFAULT 'courant', remplace_par TEXT,
    nb_pages INTEGER, pages_vides TEXT, nb_pages_sommaire INTEGER,
    statut_extraction TEXT, message_extraction TEXT, plan_source TEXT, nb_titres INTEGER,
    version_extracteur INTEGER, indexe_le TEXT
);
CREATE TABLE IF NOT EXISTS sections (
    doc_id TEXT NOT NULL, ordre INTEGER NOT NULL, numero TEXT, titre TEXT, page INTEGER,
    PRIMARY KEY (doc_id, ordre)
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, ordre INTEGER NOT NULL,
    page INTEGER NOT NULL, page_imprimee TEXT, section_num TEXT, section_titre TEXT,
    texte TEXT NOT NULL, sommaire INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS passages_doc ON passages(doc_id, page);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    texte, section_titre, content='passages', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);
"""


def connecter(chemin: Path | None = None) -> sqlite3.Connection:
    chemin = chemin or chemins.index_db()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(chemin)
    cx.row_factory = sqlite3.Row
    cx.executescript(SCHEMA)
    return cx


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# ---------------------------------------------------------------- manifeste

def lire_manifeste() -> dict:
    p = chemins.manifeste()
    if not p.exists():
        return {"documents": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def ecrire_manifeste(m: dict) -> None:
    p = chemins.manifeste()
    p.parent.mkdir(parents=True, exist_ok=True)
    m["documents"] = dict(sorted(m["documents"].items(), key=lambda kv: kv[1].get("doc_id", "")))
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def catalogue() -> dict:
    return json.loads(chemins.catalogue().read_text(encoding="utf-8"))


# ---------------------------------------------------------------- détection des métadonnées

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "january": 1, "february": 2,
        "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12}
_NOMS_MOIS = "|".join(MOIS)
RE_DATES = [
    (re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"\b(20\d{2})\s?[-/ ]\s?(\d{2})\s?[-/ ]\s?(\d{2})\b"), lambda m: (m[1], m[2], m[3])),
    (re.compile(rf"\b(\d{{1,2}})(?:er|st|nd|rd|th)?\s+({_NOMS_MOIS})\s+(20\d{{2}})\b"), lambda m: (m[3], MOIS[m[2]], m[1])),
    (re.compile(rf"\b({_NOMS_MOIS})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b"), lambda m: (m[3], MOIS[m[1]], m[2])),
]
RE_VERSION = re.compile(r"\bv(?:ersion)?\s?\.?\s?(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?[a-z]?)\b", re.I)
RE_VERSION_ENTETE = re.compile(r"(?:\bversion\s+v?|\bv)(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?[a-z]?|20\d{2})\b", re.I)


def _date(textes: list[str]) -> str | None:
    """Date de publication : la plus fréquente des premières pages (elle figure dans
    l'en-tête ou le pied de chaque page)."""
    vues = Counter()
    for t in textes:
        tn = sans_accents(re.sub(r"\s+", " ", t.lower()))
        for rx, conv in RE_DATES:
            for m in rx.finditer(tn):
                try:
                    a, mo, j = (int(x) for x in conv(m))
                except (ValueError, KeyError):
                    continue
                if 1 <= mo <= 12 and 1 <= j <= 31 and 2000 <= a <= 2100:
                    vues[f"{a:04d}-{mo:02d}-{j:02d}"] += 1
    return vues.most_common(1)[0][0] if vues else None


def _version(nom: str, titre: str, textes: list[str]) -> str | None:
    """Version déclarée : celle de l'en-tête répété (« Version 2014 », « v4.0 GA »), sinon
    celle du nom de fichier ou du titre PDF. L'historique des révisions, qui cite toutes
    les versions antérieures une seule fois, ne l'emporte donc pas."""
    pages = Counter()
    for t in textes:
        pages.update({m.group(1).lower() for m in RE_VERSION_ENTETE.finditer(t)})
    if pages and pages.most_common(1)[0][1] >= 2:
        return pages.most_common(1)[0][0]
    for source in (nom.replace("_", " "), titre):
        m = RE_VERSION.search(source)
        if m:
            return m.group(1)
    if pages:
        return pages.most_common(1)[0][0]
    m = re.search(r"\b(20\d{2})\b", nom)
    return m.group(1) if m else None


def _langue(texte: str) -> str:
    mots = normaliser(texte).split()
    fr = sum(m in {"le", "la", "les", "des", "est", "et", "pour", "une", "dans", "du"} for m in mots)
    en = sum(m in {"the", "and", "of", "is", "to", "for", "in", "with", "are", "be"} for m in mots)
    return "fr" if fr > en else "en"


def _type(texte: str) -> str:
    t = normaliser(texte)
    if "body of knowledge" in t or "ensemble des connaissances" in t:
        return "bok"
    if "glossa" in t:
        return "glossaire"
    if "release notes" in t or "notes de version" in t:
        return "notes"
    if "sample exam" in t or "examen blanc" in t or "exam questions" in t:
        return "examen"
    return "syllabus" if "syllabus" in t else "document"


def entree_catalogue(zones: list[str]) -> dict | None:
    """Entrée du catalogue reconnue dans la première zone qui en mentionne une
    (zones de la plus fiable à la moins fiable ; motifs du plus spécifique au plus général)."""
    for zone in zones:
        zn = normaliser(zone)
        for e in catalogue()["documents"]:
            if any(re.search(rx, zn) for rx in e["motifs"]):
                return e
    return None


def detecter(chemin: Path, ext: extraction.Extraction) -> dict:
    """Métadonnées déduites du nom de fichier, des métadonnées PDF et de la couverture.
    Seule la couverture compte pour le code : les pages suivantes citent d'autres syllabus."""
    nom = chemin.stem.replace("_", " ").replace("-", " ")
    titre_pdf = ext.meta_pdf.get("Title", "")
    if titre_pdf.lower().startswith("microsoft word") or len(titre_pdf) < 6:
        titre_pdf = ""
    couverture = ext.brut_debut[0] if ext.brut_debut else ""
    entete = "\n".join(ext.brut_debut[:3])
    entree = entree_catalogue([nom, titre_pdf, couverture, entete])
    code = entree["code"] if entree else None
    corps = " ".join(p.texte for p in ext.pages[:12])
    meta = {
        "code": code,
        "type": _type(f"{nom} {titre_pdf} {couverture}"),
        "langue": _langue(corps),
        "version": _version(chemin.name, titre_pdf, ext.brut_debut),
        "date_publication": _date(ext.brut_debut),
        "niveau": entree["niveau"] if entree else None,
        "domaine": entree["domaine"] if entree else None,
        "page_officielle": entree["page_officielle"] if entree else None,
    }
    lib = (entree["titre"] if entree else (titre_pdf or chemin.stem))
    suffixe = {"bok": " — Body of Knowledge", "glossaire": " — Glossaire", "notes": " — Notes de version",
               "examen": " — Examen blanc"}.get(meta["type"], "")
    meta["titre"] = f"ISTQB {lib}{suffixe}" if entree else lib
    return meta


def _doc_id(meta: dict, sha: str, pris: set[str]) -> str:
    if meta.get("code"):
        base = meta["code"] + ("-BoK" if meta.get("type") == "bok" else "") + \
            (f"-{meta['type']}" if meta.get("type") in ("glossaire", "notes", "examen") else "") + \
            f"-{meta.get('version') or 'v?'}-{meta.get('langue') or 'xx'}"
    else:
        base = re.sub(r"[^A-Za-z0-9.]+", "-", meta.get("titre") or sha[:8]).strip("-")[:50]
    return base if base not in pris else f"{base}-{sha[:6]}"


# ---------------------------------------------------------------- versions

def _cle_version(v: str | None) -> tuple:
    if not v:
        return ()
    parts = re.findall(r"\d+|[a-z]", v.lower())
    return tuple(int(p) if p.isdigit() else ord(p) - 96 for p in parts)


def _numero_version(v: str | None) -> tuple:
    """Numéro comparable, ou () pour une « version » qui est une année (2019) ou absente."""
    cle = _cle_version(v)
    return () if not cle or cle[0] >= 1900 else cle


def _comparer_versions(a, b) -> int:
    va, vb = _numero_version(a["version"]), _numero_version(b["version"])
    if va and vb and va != vb:
        return 1 if va > vb else -1
    da, db = a["date_publication"], b["date_publication"]
    if da and db and da != db:
        return 1 if da > db else -1
    return 0


def calculer_versions(cx: sqlite3.Connection) -> list[str]:
    """Pour chaque (code, type, langue), la version la plus récente est « courant »,
    les autres « remplace ». Deux numéros de version comparables (« 3.0 », « 4.0 ») font
    foi ; sinon (version « 2019 », numéro absent) on compare les dates. Faute de critère
    commun, l'ordre est signalé comme incertain (corriger la date ou la version)."""
    notes = []
    groupes: dict[tuple, list] = {}
    for r in cx.execute("SELECT doc_id, code, type, langue, version, date_publication, statut_version "
                        "FROM documents WHERE code IS NOT NULL AND statut_extraction != 'absent'"):
        groupes.setdefault((r["code"], r["type"], r["langue"]), []).append(r)
    cx.execute("UPDATE documents SET statut_version='courant', remplace_par=NULL")
    for (code, typ, langue), docs in groupes.items():
        if len(docs) < 2:
            continue
        docs.sort(key=cmp_to_key(_comparer_versions), reverse=True)
        tete = docs[0]
        for r in docs[1:]:
            if _comparer_versions(tete, r) == 0 and r["version"] != tete["version"]:
                notes.append(f"ordre incertain entre {tete['doc_id']} et {r['doc_id']} (date ou numéro de "
                             "version manquant) : `corriger <doc_id> --date AAAA-MM-JJ`")
            cx.execute("UPDATE documents SET statut_version='remplace', remplace_par=? WHERE doc_id=?",
                       (tete["doc_id"], r["doc_id"]))
            meme = (r["version"] == tete["version"])
            notes.append(f"{r['doc_id']} {'(même version déclarée, fichier différent) ' if meme else ''}"
                         f"remplacé par {tete['doc_id']} pour {code} {typ} [{langue}]")
    cx.execute("UPDATE documents SET statut_version='absent' WHERE statut_extraction='absent'")
    return notes


# ---------------------------------------------------------------- indexation

def _indexer(cx: sqlite3.Connection, doc_id: str, ext: extraction.Extraction) -> int:
    cx.execute("DELETE FROM passages_fts WHERE rowid IN (SELECT id FROM passages WHERE doc_id=?)", (doc_id,))
    cx.execute("DELETE FROM passages WHERE doc_id=?", (doc_id,))
    cx.execute("DELETE FROM sections WHERE doc_id=?", (doc_id,))
    cx.executemany("INSERT INTO sections(doc_id, ordre, numero, titre, page) VALUES (?,?,?,?,?)",
                   [(doc_id, i, t.numero, t.titre, t.page) for i, t in enumerate(ext.plan)])
    n = 0
    for i, p in enumerate(extraction.passages(ext)):
        cur = cx.execute("INSERT INTO passages(doc_id, ordre, page, page_imprimee, section_num, section_titre, "
                         "texte, sommaire) VALUES (?,?,?,?,?,?,?,?)",
                         (doc_id, i, p.page, p.imprimee, p.section_num, p.section_titre, p.texte, int(p.sommaire)))
        cx.execute("INSERT INTO passages_fts(rowid, texte, section_titre) VALUES (?,?,?)",
                   (cur.lastrowid, p.texte, p.section_titre))
        n += 1
    return n


def _enregistrer(cx, entree: dict, ext: extraction.Extraction) -> int:
    statut, message = ext.statut()
    cx.execute("DELETE FROM documents WHERE sha256=? OR doc_id=?", (entree["sha256"], entree["doc_id"]))
    champs = ("titre", "code", "type", "niveau", "domaine", "version", "langue", "date_publication",
              "source_officielle", "page_officielle")
    cx.execute(
        f"INSERT INTO documents(doc_id, sha256, fichier, {', '.join(champs)}, nb_pages, pages_vides, "
        "nb_pages_sommaire, statut_extraction, message_extraction, plan_source, nb_titres, version_extracteur, "
        f"indexe_le) VALUES ({', '.join('?' * (len(champs) + 12))})",
        (entree["doc_id"], entree["sha256"], entree["fichier"], *[entree.get(c) for c in champs],
         ext.nb_pages, ",".join(map(str, ext.pages_vides())), sum(p.sommaire for p in ext.pages),
         statut, message, ext.plan_source, len(ext.plan), extraction.VERSION_EXTRACTEUR,
         datetime.now().isoformat(timespec="seconds")))
    return _indexer(cx, entree["doc_id"], ext) if statut in ("ok", "partiel") else 0


def importer(fichier: Path, meta_forcee: dict | None = None, copier: bool = True,
             cx: sqlite3.Connection | None = None) -> dict:
    """Importe un fichier dans la bibliothèque. Renvoie un rapport :
    {etat: 'importe'|'doublon'|'echec'|'reindexe', doc_id, message, ...}."""
    fichier = Path(fichier)
    meta_forcee = {k: v for k, v in (meta_forcee or {}).items() if v}
    if fichier.suffix.lower() not in EXTENSIONS:
        return {"etat": "echec", "fichier": fichier.name, "message": f"format non pris en charge ({fichier.suffix})"}
    sha = empreinte(fichier)
    manif = lire_manifeste()
    propre = cx is None
    cx = cx or connecter()
    try:
        if sha in manif["documents"]:
            existant = manif["documents"][sha]
            cible = chemins.sources() / existant["fichier"]
            if cible.resolve() != fichier.resolve():
                if not cible.exists() and copier:  # source perdue : on la restaure
                    shutil.copy2(fichier, cible)
                return {"etat": "doublon", "fichier": fichier.name, "doc_id": existant["doc_id"],
                        "message": f"contenu identique (SHA-256) à {existant['fichier']} — non réimporté"}
            if meta_forcee:  # même fichier, métadonnées corrigées
                existant.update(meta_forcee)
                existant["champs_forces"] = sorted(set(existant.get("champs_forces", [])) | set(meta_forcee))
        ext = extraction.extraire(fichier)
        if sha in manif["documents"]:
            entree = manif["documents"][sha]
        else:
            meta = detecter(fichier, ext)
            meta.update(meta_forcee)
            pris = {e["doc_id"] for e in manif["documents"].values()}
            entree = {"sha256": sha, "doc_id": _doc_id(meta, sha, pris), **meta,
                      "source_officielle": meta_forcee.get("source_officielle"),
                      "origine": meta_forcee.get("origine", "import manuel"),
                      "importe_le": datetime.now().date().isoformat(),
                      "champs_forces": sorted(meta_forcee)}
            nom = fichier.name
            if copier:
                chemins.sources().mkdir(parents=True, exist_ok=True)
                cible = chemins.sources() / nom
                if cible.exists() and empreinte(cible) != sha:
                    nom = f"{fichier.stem}-{sha[:6]}{fichier.suffix}"
                    cible = chemins.sources() / nom
                if cible.resolve() != fichier.resolve():
                    shutil.copy2(fichier, cible)
            entree["fichier"] = nom
            manif["documents"][sha] = entree
        n = _enregistrer(cx, entree, ext)
        notes = [n for n in calculer_versions(cx) if entree["doc_id"] in n]
        cx.commit()
        ecrire_manifeste(manif)
        statut, message = ext.statut()
        return {"etat": "importe" if statut in ("ok", "partiel") else "echec", "fichier": fichier.name,
                "doc_id": entree["doc_id"], "passages": n, "statut_extraction": statut, "message": message,
                "versions": notes, "meta": {k: entree.get(k) for k in
                                            ("titre", "code", "type", "version", "langue", "date_publication")}}
    finally:
        if propre:
            cx.close()


def actualiser(forcer: bool = False) -> dict:
    """Synchronise l'index avec bibliotheque/sources/ : nouveaux fichiers importés,
    fichiers modifiés ou extraits par un ancien extracteur réindexés, fichiers
    disparus signalés. Ne supprime jamais un fichier source."""
    rapport = {"importes": [], "reindexes": [], "modifies": [], "inchanges": 0, "doublons": [], "absents": [],
               "echecs": [], "versions": []}
    manif = lire_manifeste()
    cx = connecter()
    try:
        connus = {r["sha256"]: dict(r) for r in cx.execute("SELECT * FROM documents")}
        presents = set()
        dossier = chemins.sources()
        dossier.mkdir(parents=True, exist_ok=True)
        for f in sorted(dossier.iterdir()):
            if f.suffix.lower() not in EXTENSIONS or f.name.startswith(".") or f.name.lower() in IGNORES:
                continue
            sha = empreinte(f)
            if sha in presents:
                rapport["doublons"].append(f"{f.name} (contenu identique à un autre fichier source)")
                continue
            presents.add(sha)
            entree = manif["documents"].get(sha)
            if entree is None:
                # Même nom, contenu modifié sur place (fichier corrigé, PDF ré-exporté) : on
                # reprend l'entrée existante (doc_id et corrections manuelles conservés).
                ancien = next((k for k, e in manif["documents"].items() if e["fichier"] == f.name), None)
                if ancien:
                    entree = manif["documents"].pop(ancien)
                    entree["sha256"] = sha
                    manif["documents"][sha] = entree
                    cx.execute("DELETE FROM documents WHERE sha256=?", (ancien,))
                    rapport["modifies"].append(f"{entree['doc_id']} ({f.name}) : contenu modifié, réindexé")
            if entree and entree["fichier"] != f.name:
                if (dossier / entree["fichier"]).exists():
                    rapport["doublons"].append(f"{f.name} = {entree['fichier']}")
                    continue
                entree["fichier"] = f.name  # fichier renommé
                cx.execute("UPDATE documents SET fichier=? WHERE sha256=?", (f.name, sha))
            doc = connus.get(sha)
            if entree and doc and not forcer and doc["version_extracteur"] == extraction.VERSION_EXTRACTEUR \
                    and doc["statut_extraction"] != "absent":
                rapport["inchanges"] += 1
                continue
            if entree:
                ext = extraction.extraire(f)
                # Détection améliorée depuis le dernier passage : on rafraîchit les champs
                # détectés, jamais ceux que l'utilisateur a corrigés (`champs_forces`).
                for k, v in detecter(f, ext).items():
                    if k not in entree.get("champs_forces", []) and v:
                        entree[k] = v
                _enregistrer(cx, entree, ext)
                rapport["reindexes"].append(entree["doc_id"])
            else:
                # importer() relit et réécrit le manifeste : on y enregistre d'abord les
                # changements faits en mémoire (renommages, métadonnées rafraîchies).
                ecrire_manifeste(manif)
                r = importer(f, copier=False, cx=cx)
                manif = lire_manifeste()
                (rapport["importes"] if r["etat"] == "importe" else rapport["echecs"]).append(
                    f"{r.get('doc_id', f.name)} : {r['message']}")
        for sha, entree in manif["documents"].items():
            if sha not in presents:
                rapport["absents"].append(f"{entree['doc_id']} ({entree['fichier']})")
                cx.execute("DELETE FROM passages_fts WHERE rowid IN (SELECT id FROM passages WHERE doc_id=?)",
                           (entree["doc_id"],))
                cx.execute("DELETE FROM passages WHERE doc_id=?", (entree["doc_id"],))
                cx.execute("UPDATE documents SET statut_extraction='absent', message_extraction="
                           "'fichier source introuvable dans bibliotheque/sources/' WHERE sha256=?", (sha,))
        rapport["versions"] = calculer_versions(cx)
        cx.commit()
        ecrire_manifeste(manif)
    finally:
        cx.close()
    return rapport


def retirer(doc_id: str) -> dict:
    """Retire un document de la bibliothèque (manifeste + index). Le fichier source n'est
    pas supprimé : le déplacer hors de sources/ pour qu'`actualiser` ne le réimporte pas."""
    manif = lire_manifeste()
    sha = next((s for s, e in manif["documents"].items() if e["doc_id"] == doc_id), None)
    if not sha:
        raise KeyError(f"Document inconnu : {doc_id}. Voir `inventaire`.")
    entree = manif["documents"].pop(sha)
    ecrire_manifeste(manif)
    cx = connecter()
    try:
        cx.execute("DELETE FROM passages_fts WHERE rowid IN (SELECT id FROM passages WHERE doc_id=?)", (doc_id,))
        for table in ("passages", "sections", "documents"):
            cx.execute(f"DELETE FROM {table} WHERE doc_id=?", (doc_id,))
        calculer_versions(cx)
        cx.commit()
    finally:
        cx.close()
    return entree


def modifier_metadonnees(doc_id: str, **champs) -> dict:
    """Corrige les métadonnées d'un document (détection fautive). Les champs saisis sont
    marqués « forcés » dans le manifeste et prévalent sur la détection."""
    manif = lire_manifeste()
    cible = next((s for s, e in manif["documents"].items() if e["doc_id"] == doc_id), None)
    if not cible:
        raise KeyError(f"Document inconnu : {doc_id}. Voir `inventaire`.")
    champs = {k: v for k, v in champs.items() if v is not None}
    entree = manif["documents"][cible]
    entree.update(champs)
    entree["champs_forces"] = sorted(set(entree.get("champs_forces", [])) | set(champs))
    ecrire_manifeste(manif)
    cx = connecter()
    try:
        for k, v in champs.items():
            cx.execute(f"UPDATE documents SET {k}=? WHERE sha256=?", (v, cible))
        calculer_versions(cx)
        cx.commit()
    finally:
        cx.close()
    return entree


def inventaire(cx: sqlite3.Connection | None = None) -> list[dict]:
    propre = cx is None
    cx = cx or connecter()
    try:
        return [dict(r) for r in cx.execute(
            "SELECT d.*, (SELECT COUNT(*) FROM passages p WHERE p.doc_id=d.doc_id) AS nb_passages "
            "FROM documents d ORDER BY d.niveau, d.code, d.langue, d.date_publication DESC")]
    finally:
        if propre:
            cx.close()
