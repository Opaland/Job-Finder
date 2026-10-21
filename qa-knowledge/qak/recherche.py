"""Recherche plein texte dans la bibliothèque (SQLite FTS5, classement BM25).

Une question en langage naturel devient une liste de « groupes » :
- chaque concept du thésaurus repéré donne un groupe OU de tous ses termes FR/EN
  (« partitions d'équivalence » cherche aussi « equivalence partitioning ») ;
- chaque mot restant (hors mots vides et mots génériques) forme son propre groupe.
Les candidats (OU de tous les groupes, classés BM25) sont reclassés par COUVERTURE :
part pondérée des notions de la question présentes dans le passage (un concept du
thésaurus pèse 2, un mot isolé 1), BM25 départageant les ex æquo. Un passage qui ne
couvre pas toutes les notions est marqué « partiel ».
Ce choix a été mesuré sur eval/requetes.json (voir docs/architecture.md) : le mode
« ET strict puis OU » échouait dès qu'un mot secondaire de la question manquait.
"""
import json
import re
import sqlite3
from dataclasses import dataclass

from . import bibliotheque, taxonomie
from .textes import MOTS_GENERIQUES, normaliser, reperer_concepts

CANDIDATS = 300  # passages BM25 reclassés par couverture
# Sections périphériques (annexes, notes de version, bibliographie, matrices de traçabilité) :
# elles citent beaucoup de notions sans les traiter. Rétrogradées à couverture égale.
RE_PERIPHERIQUE = re.compile(r"\b(appendi|annexe|release notes|notes de (version|release)|references|bibliograph|"
                             r"business outcomes|objectifs metier|tracabilite|traceability matrix|index)", re.I)


@dataclass
class Groupe:
    libelle: str
    termes: list[str]
    poids: int = 1

    def fts(self) -> str:
        phrases = sorted({normaliser(t) for t in self.termes if normaliser(t)})
        return "(" + " OR ".join(f'"{p}"' for p in phrases) + ")"


def sigles(requete: str) -> set[str]:
    """Sigles écrits en majuscules (SQL, GUI, ISO, API) : courts mais porteurs de sens."""
    return {normaliser(m) for m in re.findall(r"\b[A-Z][A-Z0-9]{1,5}\b", requete)}


def groupes(requete: str) -> list[Groupe]:
    concepts, reste = reperer_concepts(requete)
    garder = sigles(requete)
    out = [Groupe(cid, list(termes), 1 if cid.startswith("lex-") else 2) for cid, termes in concepts]
    out += [Groupe(m, [m]) for m in reste if m not in MOTS_GENERIQUES and (len(m) > 3 or m in garder)]
    return out


def mots_ignores(requete: str) -> list[str]:
    _, reste = reperer_concepts(requete)
    garder = sigles(requete)
    return [m for m in reste if m not in MOTS_GENERIQUES and len(m) <= 3 and m not in garder and not m.isdigit()]


def chercher(requete: str, n: int = 8, docs: list[str] | None = None, niveau: str | None = None,
             langue: str | None = None, section: str | None = None, theme: str | None = None,
             toutes_versions: bool = False, inclure_sommaires: bool = False, par_doc: int = 3,
             cx: sqlite3.Connection | None = None) -> dict:
    """Renvoie {requete_fts, groupes, resultats:[...], avertissements:[...]}."""
    gs = groupes(requete)
    avert = []
    obligatoire = None
    if theme:
        th = taxonomie.theme(theme)
        obligatoire = Groupe(f"thème {th['code']}", th["mots_cles"])
    if not gs and not obligatoire:
        return {"requete_fts": "", "groupes": [], "resultats": [],
                "avertissements": ["Requête vide après retrait des mots vides : préciser les notions cherchées."]}
    filtres, params = [], []
    if not toutes_versions:
        # Un doc_id précis demandé explicitement (même remplacé) reste cherchable.
        exacts = [d for d in (docs or []) if "-" in d and any(c.isdigit() for c in d)]
        filtres.append("(d.statut_version = 'courant'"
                       + (f" OR d.doc_id COLLATE NOCASE IN ({', '.join('?' * len(exacts))})" if exacts else "") + ")")
        params += exacts
    if not inclure_sommaires:
        filtres.append("p.sommaire = 0")
    if docs:
        conds = []
        for d in docs:
            conds.append("(d.doc_id = ? COLLATE NOCASE OR d.code = ? COLLATE NOCASE)")
            params += [d, d]
        filtres.append("(" + " OR ".join(conds) + ")")
    if niveau:
        filtres.append("d.niveau = ?")
        params.append(niveau)
    if langue:
        filtres.append("d.langue = ?")
        params.append(langue)
    if section:
        filtres.append("(p.section_num = ? OR p.section_num LIKE ?)")
        params += [section, section.rstrip(".") + ".%"]
    where = (" AND " + " AND ".join(filtres)) if filtres else ""

    def executer(expr: str, limite: int) -> list[sqlite3.Row]:
        sql = ("SELECT p.id, p.doc_id, p.page, p.page_imprimee, p.section_num, p.section_titre, p.texte, "
               "d.titre, d.code, d.version, d.langue, d.date_publication, d.statut_version, d.type, "
               "snippet(passages_fts, 0, '«', '»', ' … ', 32) AS extrait, "
               "bm25(passages_fts, 1.0, 4.0) AS score "
               "FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid "
               "JOIN documents d ON d.doc_id = p.doc_id "
               f"WHERE passages_fts MATCH ?{where} ORDER BY score LIMIT ?")
        return cx.execute(sql, [expr, *params, limite]).fetchall()

    propre = cx is None
    cx = cx or bibliotheque.connecter()
    try:
        if not cx.execute("SELECT 1 FROM passages LIMIT 1").fetchone():
            return {"requete_fts": "", "groupes": [g.libelle for g in gs], "resultats": [],
                    "avertissements": ["Bibliothèque vide : lancer `actualiser` ou `telecharger` d'abord."]}
        prefixe = f"{obligatoire.fts()} AND " if obligatoire else ""
        ou = prefixe + "(" + " OR ".join(g.fts() for g in gs) + ")" if gs else obligatoire.fts()
        candidats = executer(ou, CANDIDATS)
        ids = [r["id"] for r in candidats]
        trouves: dict[int, set[int]] = {i: set() for i in ids}
        marque = ",".join("?" * len(ids))
        for k, g in enumerate(gs):
            for (rid,) in cx.execute(f"SELECT rowid FROM passages_fts WHERE passages_fts MATCH ? "
                                     f"AND rowid IN ({marque})", [g.fts(), *ids]) if ids else []:
                trouves[rid].add(k)
        total = sum(g.poids for g in gs) or 1

        def couverture(r) -> float:
            return sum(gs[k].poids for k in trouves[r["id"]]) / total

        def peripherique(r) -> bool:
            return bool(RE_PERIPHERIQUE.search(normaliser(r["section_titre"] or "")))

        # tri stable : couverture décroissante, sections de fond d'abord, puis l'ordre BM25
        classes = sorted(candidats, key=lambda r: (-couverture(r), peripherique(r)))
        vus, resultats, par = set(), [], {}
        for r in classes:
            cle = (r["doc_id"], r["page"])
            if cle in vus or par.get(r["doc_id"], 0) >= par_doc:
                continue
            vus.add(cle)
            par[r["doc_id"]] = par.get(r["doc_id"], 0) + 1
            c = couverture(r)
            resultats.append({**{k: r[k] for k in r.keys() if k not in ("texte", "score")},
                              "score": round(-r["score"], 2), "couverture": round(c, 2),
                              "partiel": c < 1 and bool(gs),
                              "groupes_trouves": [gs[k].libelle for k in sorted(trouves[r["id"]])]})
            if len(resultats) >= n:
                break
        ignores = mots_ignores(requete)
        if ignores:
            avert.append(f"Mots trop courts ignorés : {', '.join(ignores)} (écrire un sigle en MAJUSCULES pour le garder).")
        if not resultats:
            avert.append("Aucun passage trouvé dans la bibliothèque locale : reformuler (termes anglais des "
                         "syllabus), élargir les filtres, ou justifier une recherche Web.")
        elif all(r["partiel"] for r in resultats) and len(gs) > 1:
            avert.append("Aucun passage ne couvre toutes les notions : résultats partiels.")
        manquants = [d for d in (docs or []) if not cx.execute(
            "SELECT 1 FROM documents WHERE doc_id=? COLLATE NOCASE OR code=? COLLATE NOCASE", (d, d)).fetchone()]
        if manquants:
            avert.append(f"Document(s) absent(s) de la bibliothèque : {', '.join(manquants)}.")
        return {"requete_fts": ou, "groupes": [g.libelle for g in gs], "resultats": resultats,
                "avertissements": avert}
    finally:
        if propre:
            cx.close()


def lire_passage(pid: int, contexte: int = 0, cx: sqlite3.Connection | None = None) -> list[dict]:
    """Le passage `pid` et ses `contexte` voisins de part et d'autre (même document)."""
    propre = cx is None
    cx = cx or bibliotheque.connecter()
    try:
        r = cx.execute("SELECT doc_id, ordre FROM passages WHERE id=?", (pid,)).fetchone()
        if not r:
            raise KeyError(f"Passage {pid} introuvable (index reconstruit depuis ? relancer la recherche).")
        return [dict(x) for x in cx.execute(
            "SELECT p.*, d.titre, d.code, d.version, d.langue, d.statut_version, d.date_publication "
            "FROM passages p JOIN documents d ON d.doc_id=p.doc_id "
            "WHERE p.doc_id=? AND p.ordre BETWEEN ? AND ? ORDER BY p.ordre",
            (r["doc_id"], r["ordre"] - contexte, r["ordre"] + contexte))]
    finally:
        if propre:
            cx.close()


def _doc(cx, doc: str) -> sqlite3.Row:
    r = cx.execute("SELECT * FROM documents WHERE doc_id=? COLLATE NOCASE", (doc,)).fetchone() or \
        cx.execute("SELECT * FROM documents WHERE code=? COLLATE NOCASE ORDER BY statut_version='courant' DESC, "
                   "date_publication DESC", (doc,)).fetchone()
    if not r:
        raise KeyError(f"Document inconnu : {doc}. Voir `inventaire`.")
    return r


def lire_pages(doc: str, debut: int, fin: int | None = None, cx: sqlite3.Connection | None = None) -> dict:
    propre = cx is None
    cx = cx or bibliotheque.connecter()
    try:
        d = _doc(cx, doc)
        rows = [dict(x) for x in cx.execute(
            "SELECT * FROM passages WHERE doc_id=? AND page BETWEEN ? AND ? ORDER BY ordre",
            (d["doc_id"], debut, fin or debut))]
        return {"document": dict(d), "passages": rows}
    finally:
        if propre:
            cx.close()


def lire_section(doc: str, numero: str, cx: sqlite3.Connection | None = None) -> dict:
    """Tous les passages d'une section et de ses sous-sections (« 4.2 » inclut « 4.2.1 »)."""
    propre = cx is None
    cx = cx or bibliotheque.connecter()
    try:
        d = _doc(cx, doc)
        rows = [dict(x) for x in cx.execute(
            "SELECT * FROM passages WHERE doc_id=? AND sommaire=0 AND (section_num=? OR section_num LIKE ?) "
            "ORDER BY ordre", (d["doc_id"], numero, numero.rstrip(".") + ".%"))]
        return {"document": dict(d), "passages": rows}
    finally:
        if propre:
            cx.close()


def plan(doc: str, cx: sqlite3.Connection | None = None) -> dict:
    propre = cx is None
    cx = cx or bibliotheque.connecter()
    try:
        d = _doc(cx, doc)
        return {"document": dict(d), "sections": [dict(x) for x in cx.execute(
            "SELECT numero, titre, page FROM sections WHERE doc_id=? ORDER BY ordre", (d["doc_id"],))]}
    finally:
        if propre:
            cx.close()


def compter_theme(code: str, cx: sqlite3.Connection) -> int:
    """Nombre de passages (versions courantes, hors sommaires) qui évoquent le thème."""
    th = taxonomie.theme(code)
    expr = Groupe(code, th["mots_cles"]).fts()
    return cx.execute("SELECT COUNT(*) FROM passages_fts JOIN passages p ON p.id=passages_fts.rowid "
                      "JOIN documents d ON d.doc_id=p.doc_id WHERE passages_fts MATCH ? "
                      "AND d.statut_version='courant' AND p.sommaire=0", (expr,)).fetchone()[0]


def en_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
