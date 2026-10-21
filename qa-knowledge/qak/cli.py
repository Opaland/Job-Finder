"""Interface en ligne de commande unique, appelée par le skill Claude Code.

    python qa-knowledge/qa.py <commande> [options]     (depuis la racine du dépôt)

Sorties en texte français compact ; `--json` sur les commandes de lecture pour un
traitement automatique."""
import argparse
import json
import sys
from pathlib import Path

from . import bibliotheque, catalogue, connaissances, journal, recherche, taxonomie
from .connaissances import ErreurValidation

MODELE_IDEE = {
    "titre": "Titre court et explicite",
    "resume": "Description synthétique en 1-3 phrases",
    "probleme": "Problème ou situation auquel l'idée répond",
    "principe": "Principe / technique / mode opératoire",
    "theme_principal": "code de thème (voir `themes`)",
    "themes_secondaires": ["code", "code"],
    "domaine_application": "Contexte où l'idée s'applique (type de produit, équipe, cycle)",
    "prerequis": "Conditions nécessaires",
    "benefices": "Bénéfices attendus",
    "limites": "Limites, risques, contre-indications",
    "maturite": "hypothese | documentee | pratiquee | eprouvee",
    "statut": "a_explorer | a_evaluer (validee/experimentee : via `idee statut`)",
    "provenance": "Recherche du AAAA-MM-JJ : « question posée » / saisie utilisateur",
    "references": [
        {"type": "istqb", "doc_id": "CTAL-TA-4.0-fr", "pages": "31-32", "section": "3.1.1",
         "extrait": "quelques mots copiés du passage lu (vérifiés automatiquement)"},
        {"type": "web", "titre": "Titre de la page", "url": "https://…", "note": "ce que la source apporte"},
    ],
}


def _ecrire(texte: str = "") -> None:
    sys.stdout.write(texte + "\n")


def _json(obj) -> None:
    _ecrire(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _ref_page(r: dict) -> str:
    imp = r.get("page_imprimee")
    return f"p. {r['page']}" + (f" (imprimée {imp})" if imp else "")


def _ref_doc(r: dict) -> str:
    etat = "" if r.get("statut_version", "courant") == "courant" else f" [{r['statut_version'].upper()}]"
    return f"{r['doc_id']} · {r.get('titre', '')} · v{r.get('version') or '?'} ({r.get('date_publication') or 'date ?'}){etat}"


def _lire_donnees(source: str) -> dict:
    brut = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    try:
        return json.loads(brut)
    except json.JSONDecodeError as exc:
        raise ErreurValidation(f"JSON invalide ({exc.msg}, ligne {exc.lineno}).") from exc


# ---------------------------------------------------------------- bibliothèque

def cmd_catalogue(a):
    docs = catalogue.documents(niveau=a.niveau)
    presents = {}
    if bibliotheque.chemins.index_db().exists():
        for d in bibliotheque.inventaire():
            presents.setdefault(d["code"], []).append(f"{d['langue']} v{d['version']}"
                                                      + ("" if d["statut_version"] == "courant" else "*"))
    cat = bibliotheque.catalogue()
    _ecrire(f"Catalogue ISTQB officiel — relevé le {cat['verifie_le']} ({len(docs)} syllabus)")
    for d in docs:
        ligne = f"  {d['code']:10} {d['niveau']:11} {d['titre'][:58]:58} v{d['version_constatee']:10}"
        ligne += f" local : {', '.join(presents.get(d['code'], [])) or '—'}"
        if a.verifier:
            v = catalogue.verifier(d)
            ligne += f" | {v['etat']}" + (f" ⚠ NOUVEAU FICHIER : {v['fichier']}" if v["nouveau_fichier"] else "")
        _ecrire(ligne)
    _ecrire(f"\n{cat['conditions']}")
    if not a.verifier:
        _ecrire("(--verifier interroge istqb.org pour détecter les nouvelles versions)")


def cmd_telecharger(a):
    if not (a.codes or a.tous or a.niveau):
        raise ErreurValidation("Préciser des codes (ex. CTFL CTAL-TM), --niveau ou --tous.")
    for d in catalogue.documents(None if a.tous or a.niveau else a.codes, a.niveau):
        r = catalogue.telecharger(d)
        _ecrire(f"{d['code']:10} {r['etat']:8} {r.get('doc_id', '')} — {r['message']}")
        for n in r.get("versions", []):
            _ecrire(f"           version : {n}")


def cmd_importer(a):
    meta = {"code": a.code, "titre": a.titre, "niveau": a.niveau, "domaine": a.domaine, "version": a.version,
            "langue": a.langue, "date_publication": a.date, "source_officielle": a.source, "type": a.type}
    for f in a.fichiers:
        p = Path(f)
        fichiers = sorted(x for x in p.iterdir() if x.suffix.lower() in bibliotheque.EXTENSIONS) if p.is_dir() else [p]
        for x in fichiers:
            if not x.exists():
                _ecrire(f"{x} : introuvable")
                continue
            r = bibliotheque.importer(x, meta)
            _ecrire(f"{x.name} → {r['etat']} {r.get('doc_id', '')} — {r['message']}")
            if r.get("meta"):
                m = r["meta"]
                _ecrire(f"    détecté : code={m['code']} type={m['type']} version={m['version']} "
                        f"langue={m['langue']} date={m['date_publication']} — corriger avec `corriger` si faux")
            for n in r.get("versions", []):
                _ecrire(f"    version : {n}")


def cmd_actualiser(a):
    r = bibliotheque.actualiser(forcer=a.forcer)
    _ecrire(f"Inchangés : {r['inchanges']} · importés : {len(r['importes'])} · réindexés : {len(r['reindexes'])}")
    for cle, titre in (("importes", "Importés"), ("modifies", "Modifiés sur place"), ("reindexes", "Réindexés"), ("doublons", "Doublons ignorés"),
                       ("absents", "Sources disparues (passages retirés de l'index)"), ("echecs", "ÉCHECS"),
                       ("versions", "Versions remplacées")):
        if r[cle]:
            _ecrire(f"{titre} :")
            for x in r[cle]:
                _ecrire(f"  - {x}")


def cmd_inventaire(a):
    docs = bibliotheque.inventaire()
    if a.json:
        return _json(docs)
    if not docs:
        return _ecrire("Bibliothèque vide. `telecharger --tous` (syllabus EN officiels) ou `importer <fichiers>`.")
    alertes = []
    _ecrire(f"{'document':24} {'type':8} {'niveau':11} {'date':10} {'pages':>5} {'passages':>8}  extraction / version")
    for d in docs:
        ver = "" if d["statut_version"] == "courant" else f" → remplacé par {d['remplace_par']}" \
            if d["statut_version"] == "remplace" else " (source absente)"
        _ecrire(f"{d['doc_id']:24} {d['type'] or '?':8} {d['niveau'] or '?':11} {d['date_publication'] or '?':10} "
                f"{d['nb_pages'] or 0:>5} {d['nb_passages']:>8}  {d['statut_extraction']}{ver}")
        if d["statut_extraction"] != "ok" or not d["code"] or not d["nb_titres"]:
            alertes.append(f"{d['doc_id']} : {d['statut_extraction']} — {d['message_extraction']}"
                           + ("" if d["code"] else " — code ISTQB non reconnu")
                           + ("" if d["nb_titres"] else " — aucune section détectée"))
    langues = {}
    for d in docs:
        if d["statut_version"] == "courant":
            langues.setdefault(d["langue"], set()).add(d["code"])
    _ecrire(f"\n{len(docs)} fichiers · versions courantes : "
            + ", ".join(f"{len(v)} codes en {k}" for k, v in sorted(langues.items())))
    manquants = [d["code"] for d in bibliotheque.catalogue()["documents"]
                 if not any(d["code"] in v for v in langues.values())]
    if manquants:
        _ecrire(f"Absents du catalogue officiel : {', '.join(manquants)}")
    if alertes:
        _ecrire("\nÀ surveiller :")
        for x in alertes:
            _ecrire(f"  - {x}")


def cmd_corriger(a):
    champs = {"code": a.code, "titre": a.titre, "niveau": a.niveau, "domaine": a.domaine, "version": a.version,
              "langue": a.langue, "date_publication": a.date, "source_officielle": a.source, "type": a.type}
    e = bibliotheque.modifier_metadonnees(a.doc_id, **champs)
    _ecrire(f"{a.doc_id} mis à jour (champs forcés : {', '.join(e['champs_forces'])}). "
            "L'identifiant reste inchangé ; relancer `inventaire` pour vérifier les versions.")


def cmd_retirer(a):
    e = bibliotheque.retirer(a.doc_id)
    _ecrire(f"{a.doc_id} retiré de la bibliothèque. Fichier conservé : bibliotheque/sources/{e['fichier']} "
            "(le déplacer hors du dossier, sinon `actualiser` le réimportera).")


def cmd_chercher(a):
    r = recherche.chercher(" ".join(a.requete), n=a.n, docs=a.doc, niveau=a.niveau, langue=a.langue,
                           section=a.section, theme=a.theme, toutes_versions=a.toutes_versions,
                           inclure_sommaires=a.sommaires, par_doc=a.par_doc)
    if a.json:
        return _json(r)
    _ecrire(f"Notions : {', '.join(r['groupes']) or '—'}" + (f" · thème : {a.theme}" if a.theme else ""))
    for i, x in enumerate(r["resultats"], 1):
        sec = f"§{x['section_num']} {x['section_titre']}".strip() if x["section_num"] or x["section_titre"] else "§ ?"
        _ecrire(f"\n[{i}] {_ref_doc(x)}")
        _ecrire(f"    {_ref_page(x)} · {sec} · passage #{x['id']}"
                + (" · PARTIEL : " + ", ".join(x["groupes_trouves"]) if x["partiel"] else ""))
        _ecrire(f"    {' '.join(x['extrait'].split())}")
    for w in r["avertissements"]:
        _ecrire(f"\n⚠ {w}")
    if r["resultats"]:
        _ecrire("\nLire avant de citer : `lire <passage>` (--contexte 1) ou `section <doc> <num>`.")


def _afficher_passages(rows: list[dict], doc: dict | None = None):
    courant = None
    for p in rows:
        d = doc or p
        sec = f"§{p['section_num']} {p['section_titre']}".strip()
        cle = (p["doc_id"], p["page"], sec)
        if cle != courant:
            _ecrire(f"\n── {_ref_doc({**d, 'doc_id': p['doc_id']})} · {_ref_page(p)} · {sec} (passage #{p['id']})")
            courant = cle
        _ecrire(p["texte"])


def cmd_lire(a):
    rows = recherche.lire_passage(a.passage, a.contexte)
    _json(rows) if a.json else _afficher_passages(rows)


def cmd_page(a):
    debut, _, fin = a.pages.partition("-")
    r = recherche.lire_pages(a.doc, int(debut), int(fin) if fin else None)
    if a.json:
        return _json(r)
    if not r["passages"]:
        return _ecrire(f"Aucun texte indexé pour ces pages de {r['document']['doc_id']} "
                       f"({r['document']['nb_pages']} pages ; pages vides : {r['document']['pages_vides'] or 'aucune'}).")
    _afficher_passages(r["passages"], r["document"])


def cmd_section(a):
    r = recherche.lire_section(a.doc, a.numero)
    if a.json:
        return _json(r)
    if not r["passages"]:
        return _ecrire(f"Section {a.numero} introuvable dans {r['document']['doc_id']} : voir `plan {a.doc}`.")
    _afficher_passages(r["passages"], r["document"])


def cmd_plan(a):
    r = recherche.plan(a.doc)
    if a.json:
        return _json(r)
    _ecrire(_ref_doc(r["document"]))
    for s in r["sections"]:
        if s["numero"] or a.tout:
            prof = s["numero"].count(".") if s["numero"] else 3
            _ecrire(f"{'  ' * prof}{s['numero']} {s['titre']}  (p. {s['page']})")


# ---------------------------------------------------------------- taxonomie

def cmd_themes(a):
    compte = {}
    for i in connaissances.lister():
        compte[i["theme_principal"]] = compte.get(i["theme_principal"], 0) + 1
    if a.json:
        return _json(taxonomie.themes())
    for niveau, t in taxonomie.arbre():
        etat = "" if t["statut"] == "actif" else f"  [OBSOLÈTE → {t.get('remplace_par') or '—'}]"
        nb = f"  ({compte[t['code']]} idées)" if t["code"] in compte else ""
        _ecrire(f"{'  ' * niveau}{t['code']:<{28 - 2 * niveau}} {t['libelle']}{nb}{etat}")


def cmd_theme(a):
    if a.action == "ajouter":
        t = taxonomie.ajouter(a.code, a.libelle, a.parent, [m.strip() for m in (a.mots_cles or "").split(",") if m.strip()],
                              a.motif, a.forcer)
        _ecrire(f"Thème ajouté : {taxonomie.chemin(t['code'])} ({t['code']})")
    elif a.action == "obsolete":
        taxonomie.rendre_obsolete(a.code, a.remplace_par, a.motif)
        _ecrire(f"Thème {a.code} marqué obsolète" + (f", remplacé par {a.remplace_par}" if a.remplace_par else "")
                + ". Les idées existantes gardent leur classement historique.")
    elif a.action == "proposer":
        for score, code in taxonomie.proposer(a.code):
            _ecrire(f"  {code:26} {taxonomie.chemin(code)}  (score {score})")


def cmd_couverture(a):
    rows = connaissances.couverture()
    if a.json:
        return _json(rows)
    _ecrire(f"{'thème':40} {'idées':>5} {'passages':>8}  état")
    for r in rows:
        _ecrire(f"{'  ' * r['niveau'] + r['libelle'][:38 - 2 * r['niveau']]:40} {r['idees']:>5} "
                f"{r['passages'] if r['passages'] is not None else '—':>8}  {r['etat']}")
    pistes = sorted((r for r in rows if r["etat"] != "correct" and (r["passages"] or 0) > 0),
                    key=lambda r: -(r["passages"] or 0))[:5]
    if pistes:
        _ecrire("\nThèmes pauvres en idées mais documentés dans les syllabus (pistes d'exploration) : "
                + ", ".join(f"{r['code']} ({r['passages']} passages)" for r in pistes))


# ---------------------------------------------------------------- idées

def _afficher_doublons(sim: list[dict]):
    for s in sim:
        _ecrire(f"  {s['verdict'].upper():16} {s['id']} « {s['titre']} » (similarité {s['score']}, {s['statut']})")


def cmd_idee(a):
    act = a.action
    if act == "modele":
        return _json(MODELE_IDEE)
    if act == "ajouter":
        r = connaissances.ajouter(_lire_donnees(a.fichier), forcer=a.forcer, motif=a.motif)
        if r["etat"] == "refuse":
            _ecrire(f"REFUSÉ — {r['message']}")
        else:
            _ecrire(f"Idée créée : {r['id']}")
        _afficher_doublons(r["doublons"])
        for w in r["avertissements"]:
            _ecrire(f"  ⚠ {w}")
    elif act == "doublons":
        d, _ = connaissances.valider(_lire_donnees(a.fichier), partiel=True)
        sim = connaissances.doublons(d)
        _ecrire("Aucune idée similaire." if not sim else "Idées similaires :")
        _afficher_doublons(sim)
        _ecrire("Thèmes suggérés : " + ", ".join(c for _, c in taxonomie.proposer(
            " ".join(str(d.get(k, "")) for k in ("titre", "resume", "principe")))))
    elif act == "modifier":
        r = connaissances.modifier(a.id, _lire_donnees(a.fichier), a.remplacer_listes, a.motif)
        _ecrire(f"{a.id} : {r['etat']}" + (f" ({', '.join(r['champs'])})" if r.get("champs") else ""))
        for w in r["avertissements"]:
            _ecrire(f"  ⚠ {w}")
    elif act == "statut":
        r = connaissances.changer_statut(a.id, a.statut, a.motif)
        _ecrire(f"{a.id} : {r['avant']} → {r['apres']}")
    elif act == "retour":
        r = connaissances.ajouter_retour(a.id, a.contexte, a.resultat, a.enseignement, a.date)
        _ecrire(f"{a.id} : retour d'expérience enregistré ({r['retours']} au total)")
    elif act == "lier":
        if not a.cible or not a.type:
            raise ErreurValidation("Usage : idee lier QA-xxxx QA-yyyy --type "
                                   f"{'|'.join(connaissances.RELATIONS)} [--note …]")
        r = connaissances.lier(a.id, a.cible, a.type, a.note)
        _ecrire(f"{r['source']} —{r['type']}→ {r['cible']}")
    elif act == "voir":
        i = connaissances.voir(a.id)
        if a.json:
            return _json(i)
        _ecrire(f"{i['id']} — {i['titre']}")
        _ecrire(f"Thème : {taxonomie.chemin(i['theme_principal'])}"
                + (f" · secondaires : {', '.join(i['themes_secondaires'])}" if i["themes_secondaires"] else ""))
        _ecrire(f"Statut : {connaissances.STATUTS[i['statut']]} · maturité : {i['maturite']} "
                f"({connaissances.MATURITES[i['maturite']]})")
        _ecrire(f"Créée le {i['cree_le'][:10]} · mise à jour le {i['maj_le'][:10]} · provenance : {i.get('provenance', '?')}")
        for k, lib in (("resume", "Résumé"), ("probleme", "Problème"), ("principe", "Principe"),
                       ("domaine_application", "Domaine d'application"), ("prerequis", "Prérequis"),
                       ("benefices", "Bénéfices"), ("limites", "Limites et risques")):
            if i.get(k):
                _ecrire(f"\n{lib} : {i[k]}")
        if i["references"]:
            _ecrire("\nRéférences :")
            for r in i["references"]:
                loc = " ".join(x for x in (r.get("doc_id"), f"p. {r['pages']}" if r.get("pages") else "",
                                           f"§{r['section']}" if r.get("section") else "") if x)
                _ecrire(f"  - [{r['type']}] {r.get('titre', '')} {loc} {r.get('url', '')}".rstrip()
                        + (f" — « {r['extrait']} »" if r.get("extrait") else ""))
        for r in i["relations"]:
            _ecrire(f"  → {r['type']} {r['cible']} « {r['titre']} »" + (f" ({r['note']})" if r.get("note") else ""))
        for r in i["relations_entrantes"]:
            _ecrire(f"  ← {r['type']} depuis {r['source']} « {r['titre']} »")
        for r in i["retours"]:
            _ecrire(f"\nRetour {r.get('date', '')} : {r.get('contexte', '')} → {r.get('resultat', '')}"
                    + (f" — enseignement : {r['enseignement']}" if r.get("enseignement") else ""))
    elif act == "lister":
        rows = connaissances.lister(a.theme, a.statut)
        if a.json:
            return _json(rows)
        if not rows:
            return _ecrire("Aucune idée" + (f" pour le thème {a.theme}" if a.theme else "") + ".")
        for r in rows:
            _ecrire(f"{r['id']}  {r['theme_principal']:22} {r['statut']:12} {r['maturite']:10} {r['titre']}")
    elif act == "chercher":
        rows = connaissances.chercher(" ".join(a.requete or []), theme=a.theme)
        if a.json:
            return _json(rows)
        if not rows:
            return _ecrire("Aucune idée capitalisée ne correspond.")
        for r in rows:
            _ecrire(f"{r['id']}  [{r['statut']}/{r['maturite']}] {r['titre']} ({r['theme_principal']})")
            _ecrire(f"        {' '.join(r['extrait'].split())}")
    elif act == "verifier-refs":
        rows = connaissances.verifier_references()
        ko = [r for r in rows if r["problemes"]]
        _ecrire(f"{len(rows)} références ISTQB contrôlées, {len(ko)} à revoir.")
        for r in ko:
            _ecrire(f"  {r['idee']} {r['doc_id']} p. {r['pages']} : {'; '.join(r['problemes'])}")


def cmd_journal(a):
    for e in journal.lire(a.cible, a.n):
        _ecrire(f"{e['horodatage']} {e['action']:18} {e['cible']}" + (f" — {e['motif']}" if e.get("motif") else ""))


def cmd_evaluer(a):
    from . import evaluation
    r = evaluation.evaluer(a.k, {"reglage": False, "controle": True}.get(a.jeu))
    for x in r["details"]:
        _ecrire(f"{'OK ' if x['trouve'] else 'KO '} rang {x['rang'] or '-':>2}  {x['requete']}  → attendu {x['attendu']}")
    _ecrire(f"\nRappel@{a.k} : {r['rappel']:.0%} ({r['trouves']}/{r['total']}) · MRR : {r['mrr']:.2f}"
            + (f" · ignorées (document absent) : {r['ignorees']}" if r["ignorees"] else ""))


# ---------------------------------------------------------------- analyseur

def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qa.py", description="QA Knowledge Agent — bibliothèque ISTQB et base QA.")
    sp = p.add_subparsers(dest="commande", required=True)

    def meta(x):
        for opt in ("code", "titre", "niveau", "domaine", "version", "langue", "date", "source", "type"):
            x.add_argument(f"--{opt}")

    x = sp.add_parser("catalogue", help="syllabus officiels ISTQB et présence locale")
    x.add_argument("--verifier", action="store_true", help="interroger istqb.org (nouvelles versions)")
    x.add_argument("--niveau", choices=["fondation", "avance", "expert", "specialiste"])
    x.set_defaults(f=cmd_catalogue)
    x = sp.add_parser("telecharger", help="télécharger des syllabus officiels (istqb.org) et les indexer")
    x.add_argument("codes", nargs="*")
    x.add_argument("--tous", action="store_true")
    x.add_argument("--niveau", choices=["fondation", "avance", "expert", "specialiste"])
    x.set_defaults(f=cmd_telecharger)
    x = sp.add_parser("importer", help="importer des PDF / .txt / .md (fichiers ou dossiers)")
    x.add_argument("fichiers", nargs="+")
    meta(x)
    x.set_defaults(f=cmd_importer)
    x = sp.add_parser("actualiser", help="réindexation incrémentale de bibliotheque/sources/")
    x.add_argument("--forcer", action="store_true", help="tout réextraire")
    x.set_defaults(f=cmd_actualiser)
    x = sp.add_parser("inventaire", help="documents indexés, versions, extractions à surveiller")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_inventaire)
    x = sp.add_parser("corriger", help="corriger les métadonnées détectées d'un document")
    x.add_argument("doc_id")
    meta(x)
    x.set_defaults(f=cmd_corriger)

    x = sp.add_parser("retirer", help="retirer un document de la bibliothèque (manifeste + index)")
    x.add_argument("doc_id")
    x.set_defaults(f=cmd_retirer)

    x = sp.add_parser("chercher", help="recherche plein texte dans la bibliothèque")
    x.add_argument("requete", nargs="+")
    x.add_argument("-n", type=int, default=8)
    x.add_argument("--doc", action="append", help="code ou doc_id (répétable)")
    x.add_argument("--niveau", choices=["fondation", "avance", "expert", "specialiste"])
    x.add_argument("--langue", choices=["fr", "en"])
    x.add_argument("--section", help="numéro de section, sous-sections incluses (ex. 4.2)")
    x.add_argument("--theme", help="code de thème de la taxonomie")
    x.add_argument("--toutes-versions", action="store_true", help="inclure les versions remplacées")
    x.add_argument("--sommaires", action="store_true", help="inclure tables des matières et index")
    x.add_argument("--par-doc", type=int, default=3, help="résultats max par document (défaut 3)")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_chercher)
    x = sp.add_parser("lire", help="lire un passage (et son contexte)")
    x.add_argument("passage", type=int)
    x.add_argument("--contexte", type=int, default=0)
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_lire)
    x = sp.add_parser("page", help="lire des pages d'un document (ex. 31 ou 31-33)")
    x.add_argument("doc")
    x.add_argument("pages")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_page)
    x = sp.add_parser("section", help="lire une section entière (sous-sections incluses)")
    x.add_argument("doc")
    x.add_argument("numero")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_section)
    x = sp.add_parser("plan", help="plan (sections) d'un document")
    x.add_argument("doc")
    x.add_argument("--tout", action="store_true", help="inclure les titres non numérotés")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_plan)

    x = sp.add_parser("themes", help="taxonomie QA")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_themes)
    x = sp.add_parser("theme", help="ajouter / rendre obsolète / proposer un thème")
    x.add_argument("action", choices=["ajouter", "obsolete", "proposer"])
    x.add_argument("code", help="code du thème (ou texte à classer pour « proposer »)")
    x.add_argument("--libelle")
    x.add_argument("--parent")
    x.add_argument("--mots-cles", help="liste séparée par des virgules (FR et EN)")
    x.add_argument("--remplace-par")
    x.add_argument("--motif")
    x.add_argument("--forcer", action="store_true")
    x.set_defaults(f=cmd_theme)
    x = sp.add_parser("couverture", help="richesse de la base par thème (et matière disponible)")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_couverture)

    x = sp.add_parser("idee", help="base de connaissances : ajouter, modifier, chercher…")
    x.add_argument("action", choices=["modele", "ajouter", "doublons", "modifier", "statut", "retour", "lier",
                                      "voir", "lister", "chercher", "verifier-refs"])
    x.add_argument("id", nargs="?", help="identifiant QA-xxxx")
    x.add_argument("requete", nargs="*", help="texte (pour chercher)")
    x.add_argument("--fichier", default="-", help="JSON de l'idée (défaut : entrée standard)")
    x.add_argument("--forcer", action="store_true")
    x.add_argument("--motif")
    x.add_argument("--remplacer-listes", action="store_true")
    x.add_argument("--statut")
    x.add_argument("--theme")
    x.add_argument("--contexte")
    x.add_argument("--resultat")
    x.add_argument("--enseignement")
    x.add_argument("--date")
    x.add_argument("--cible")
    x.add_argument("--type", choices=list(connaissances.RELATIONS))
    x.add_argument("--note")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_idee)
    x = sp.add_parser("journal", help="historique des modifications")
    x.add_argument("--cible")
    x.add_argument("-n", type=int, default=30)
    x.set_defaults(f=cmd_journal)
    x = sp.add_parser("evaluer", help="mesure la qualité de la recherche sur eval/requetes.json")
    x.add_argument("-k", type=int, default=5)
    x.add_argument("--jeu", choices=["tout", "reglage", "controle"], default="tout",
                   help="« controle » = questions jamais utilisées pour régler le moteur")
    x.set_defaults(f=cmd_evaluer)
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows
    a = analyseur().parse_args(argv)
    if a.commande == "idee":
        _normaliser_idee(a)
    try:
        a.f(a)
    except BrokenPipeError:  # sortie tronquée (`| head`) : pas une erreur
        sys.stderr.close()
        return 0
    except (ErreurValidation, KeyError, ValueError, PermissionError, FileNotFoundError) as exc:
        msg = exc.args[0] if exc.args else str(exc)
        sys.stderr.write(f"Erreur : {msg}\n")
        return 2
    return 0


def _normaliser_idee(a) -> None:
    """« idee chercher texte libre » : l'id positionnel est alors le début de la requête ;
    « idee statut QA-1 validee » : le 2e positionnel est le statut."""
    if a.action in ("chercher",):
        a.requete = ([a.id] if a.id else []) + (a.requete or [])
        a.id = None
    elif a.action == "statut" and not a.statut and a.requete:
        a.statut = a.requete[0]
    elif a.action == "lier" and not a.cible and a.requete:
        a.cible = a.requete[0]
    elif a.action == "lister" and (a.id or a.requete):
        raise SystemExit("Erreur : `idee lister` ne prend pas de texte : utiliser --theme <code> / --statut, "
                         "ou `idee chercher <texte>`.")
    besoin_id = {"modifier", "statut", "retour", "lier", "voir"}
    if a.action in besoin_id and not a.id:
        raise SystemExit(f"Erreur : `idee {a.action}` attend un identifiant (QA-xxxx).")
