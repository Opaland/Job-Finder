"""Tests du digest (relances) et de l'extraction de description complète."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Digest, Offer, Profile, STATUTS_ACTIFS, local_now
from app.services.digest import (
    GEM_SCORE,
    RELAUNCH_AFTER_DAYS,
    actions_due,
    applications_this_week,
    build_digest,
    daily_focus,
    debut_de_semaine,
    digest_html,
    next_interviews,
    offers_to_relaunch,
    resume_semaine,
    send_digest_email,
)
import app.services.digest as digest_module
from app.services.enrich import extract_main_text


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    session.add(Profile(id=1, cv_text="cv", sources_enabled={}))
    session.commit()
    yield session
    session.close()


def _offer(db, status, days_ago, title="Test Manager"):
    changed = (local_now() - timedelta(days=days_ago)).isoformat()
    offer = Offer(
        fingerprint=f"fp-{title}-{status}-{days_ago}",
        source="test", source_id=f"{title}-{status}-{days_ago}",
        title=title, company="ACME", status=status, final_score=80,
        status_history=[{"status": status, "date": changed, "par": "utilisateur"}],
    )
    db.add(offer)
    db.commit()
    return offer


def test_relance_apres_7_jours(db):
    _offer(db, "postulee", days_ago=10, title="Vieille candidature")
    _offer(db, "postulee", days_ago=2, title="Candidature récente")
    _offer(db, "relancee", days_ago=8, title="Déjà relancée il y a longtemps")
    _offer(db, "entretien", days_ago=30, title="En entretien")  # pas concernée

    titles = [o.title for o in offers_to_relaunch(db)]
    assert "Vieille candidature" in titles
    assert "Déjà relancée il y a longtemps" in titles
    assert "Candidature récente" not in titles
    assert "En entretien" not in titles


def test_digest_contient_les_relances(db):
    _offer(db, "postulee", days_ago=10, title="À relancer")
    digest = build_digest(db)
    relaunch = digest.payload["to_relaunch"]
    assert len(relaunch) == 1
    assert relaunch[0]["title"] == "À relancer"
    # Et l'email les affiche.
    assert "relancer" in digest_html(digest.payload).lower()


def test_digest_sans_relance(db):
    _offer(db, "postulee", days_ago=1)
    digest = build_digest(db)
    assert digest.payload["to_relaunch"] == []


def test_actions_a_faire_aujourdhui(db):
    """Les actions datées échues (aujourd'hui + retard) remontent ; le futur non."""
    from app.models import Offer

    def offer_with_action(sid, days_offset, note):
        return Offer(
            fingerprint=f"fp-act-{sid}", source="test", source_id=f"act-{sid}",
            title=f"Offre {sid}", company="ACME", status="postulee", final_score=70,
            next_action_date=local_now() + timedelta(days=days_offset),
            next_action_note=note,
        )

    db.add_all([
        offer_with_action("retard", -3, "Relancer par email"),
        offer_with_action("jour", 0, "Préparer l'entretien"),
        offer_with_action("futur", 5, "Relance semaine prochaine"),
    ])
    db.commit()

    payload = build_digest(db).payload
    todo = {a["action_note"]: a for a in payload["todo_today"]}
    assert "Relancer par email" in todo and todo["Relancer par email"]["overdue"] is True
    assert "Préparer l'entretien" in todo and todo["Préparer l'entretien"]["overdue"] is False
    assert "Relance semaine prochaine" not in todo
    assert "faire aujourd" in digest_html(payload).lower()


def test_focus_du_jour(db):
    """Le focus priorise action échue > pépite > relance, sans doublon d'offre."""
    from app.models import Offer

    db.add_all([
        Offer(fingerprint="fp-f1", source="test", source_id="f1", title="Action due",
              company="A", status="postulee", final_score=60,
              next_action_date=local_now() - timedelta(days=1), next_action_note="Rappeler la RH"),
        Offer(fingerprint="fp-f2", source="test", source_id="f2", title="Pépite ouverte",
              company="B", status="nouvelle", final_score=93),
        Offer(fingerprint="fp-f3", source="test", source_id="f3", title="Vieille candidature",
              company="C", status="postulee", final_score=70,
              status_history=[{"status": "postulee", "date": (local_now() - timedelta(days=10)).isoformat(), "par": "u"}]),
    ])
    db.commit()

    focus = build_digest(db).payload["focus"]
    assert [f["type"] for f in focus] == ["action", "pepite", "relance"]
    assert focus[0]["label"].startswith("En retard")
    assert len({f["id"] for f in focus}) == len(focus)


def test_pepites_et_objectif_hebdo(db):
    """Les offres ouvertes >= GEM_SCORE (80) sont des pépites ; les candidatures de la semaine comptent."""
    from app.models import Offer

    gem = Offer(fingerprint="fp-gem", source="test", source_id="gem",
                title="Test Manager idéal", company="ACME", status="nouvelle", final_score=92)
    pas_gem = Offer(fingerprint="fp-bof", source="test", source_id="bof",
                    title="Offre moyenne", company="ACME", status="nouvelle", final_score=60)
    gem_traitee = Offer(fingerprint="fp-traitee", source="test", source_id="traitee",
                        title="Déjà postulée", company="ACME", status="postulee", final_score=95,
                        status_history=[{"status": "postulee", "date": local_now().isoformat(), "par": "utilisateur"}])
    db.add_all([gem, pas_gem, gem_traitee])
    db.commit()

    payload = build_digest(db).payload
    gem_titles = [g["title"] for g in payload["gems"]]
    assert "Test Manager idéal" in gem_titles
    assert "Offre moyenne" not in gem_titles
    assert "Déjà postulée" not in gem_titles  # déjà traitée : plus une pépite
    # Postulée aujourd'hui (donc cette semaine) → compte dans l'objectif.
    assert payload["weekly"]["sent"] >= 1
    assert payload["weekly"]["goal"] == 5  # défaut du profil


def test_pepite_pile_au_seuil(db):
    """Frontière exacte de GEM_SCORE jamais testée auparavant (issue #20, même
    famille) : une offre tout juste au seuil doit être une pépite, une offre
    juste sous le seuil ne doit pas en être une."""
    db.add_all([
        Offer(fingerprint="fp-pile", source="test", source_id="pile", title="Pile au seuil",
              company="A", status="nouvelle", final_score=GEM_SCORE),
        Offer(fingerprint="fp-sous", source="test", source_id="sous", title="Juste sous le seuil",
              company="A", status="nouvelle", final_score=GEM_SCORE - 0.1),
    ])
    db.commit()
    gem_titles = [g["title"] for g in build_digest(db).payload["gems"]]
    assert "Pile au seuil" in gem_titles
    assert "Juste sous le seuil" not in gem_titles


def test_candidatures_a_suivre_signale_le_total_au_dela_de_15(db):
    """Issue #32 : to_follow était tronqué à 15 sans jamais exposer le total
    réel — contrairement à new_count, qui lui l'est. Au-delà de 15 candidatures
    actives, une candidature plus ancienne à score plus faible sortait du
    digest sans aucun « + N autres »."""
    for i in range(18):
        db.add(Offer(fingerprint=f"fp-suivi-{i}", source="test", source_id=str(i),
                     title="Test Manager", company="ACME", status=STATUTS_ACTIFS[i % len(STATUTS_ACTIFS)],
                     final_score=100 - i))
    db.commit()

    payload = build_digest(db).payload
    assert len(payload["to_follow"]) == 15
    assert payload["to_follow_total"] == 18


# --- Sprint 61 : trous relevés par mutation testing (digest.py) --------------

def test_constantes_relance_et_pepite(db):
    """Les seuils métier sont des constantes exportées : valeur réelle jamais
    vérifiée directement (les tests existants ne regardent que leur effet)."""
    assert RELAUNCH_AFTER_DAYS == 7
    assert GEM_SCORE == 80


def test_debut_de_semaine_est_bien_minuit_pile(db):
    lundi = debut_de_semaine()
    assert (lundi.hour, lundi.minute, lundi.second, lundi.microsecond) == (0, 0, 0, 0)
    assert lundi.weekday() == 0


def test_gems_plafonne_a_dix(db):
    for i in range(12):
        db.add(Offer(fingerprint=f"fp-gem{i}", source="test", source_id=f"gem{i}",
                     title="Test Manager", company="ACME", status="nouvelle",
                     final_score=GEM_SCORE + i))
    db.commit()
    from app.services.digest import gems
    assert len(gems(db)) == 10


def test_top_overall_plafonne_a_dix(db):
    for i in range(12):
        db.add(Offer(fingerprint=f"fp-top{i}", source="test", source_id=f"top{i}",
                     title="Test Manager", company="ACME", status="nouvelle", final_score=50 + i))
    db.commit()
    assert len(build_digest(db).payload["top_overall"]) == 10


def test_nouvelles_offres_tronquees_a_25_mais_new_count_exact(db):
    for i in range(26):
        db.add(Offer(fingerprint=f"fp-new{i}", source="test", source_id=f"new{i}",
                     title="Test Manager", company="ACME", status="nouvelle",
                     final_score=50 + i, collected_at=local_now()))
    db.commit()
    payload = build_digest(db).payload
    assert payload["new_count"] == 26
    assert len(payload["new_offers"]) == 25


def test_nouvelles_offres_fenetre_de_26_heures_frontiere_exacte(db, monkeypatch):
    """`since = local_now() - timedelta(hours=26)` : une offre collectée à
    26h00 pile est encore une « nouvelle offre » ; à 26h30, elle ne l'est
    déjà plus. Avec une marge de seulement 30 min, un `26` muté en `27`
    élargit la fenêtre à 27h — assez pour admettre à tort l'offre à 26h30."""
    maintenant_fixe = local_now()
    monkeypatch.setattr(digest_module, "local_now", lambda: maintenant_fixe)
    db.add_all([
        Offer(fingerprint="fp-26h", source="test", source_id="h26", title="Pile 26h",
             company="ACME", status="nouvelle", final_score=70,
             collected_at=maintenant_fixe - timedelta(hours=26)),
        Offer(fingerprint="fp-26h30", source="test", source_id="h26h30", title="26h30, trop vieille",
             company="ACME", status="nouvelle", final_score=70,
             collected_at=maintenant_fixe - timedelta(hours=26, minutes=30)),
    ])
    db.commit()
    titres = [o["title"] for o in build_digest(db).payload["new_offers"]]
    assert "Pile 26h" in titres
    assert "26h30, trop vieille" not in titres


def test_applications_this_week_compte_juste_et_ignore_les_dates_illisibles(db):
    """`count += 1` (pas +=2) et `applied is not None and applied >= monday` :
    une date illisible (parse_iso_dt → None) ne doit jamais faire planter le
    calcul, et le compte doit être exact, pas doublé."""
    monday = debut_de_semaine()
    offre_cette_semaine = Offer(
        fingerprint="fp-sem1", source="test", source_id="sem1", title="Test Manager",
        company="ACME", status="postulee",
        status_history=[{"status": "postulee", "date": monday.isoformat(), "par": "u"}],
    )
    offre_date_illisible = Offer(
        fingerprint="fp-sem2", source="test", source_id="sem2", title="QA Engineer",
        company="ACME", status="postulee",
        status_history=[{"status": "postulee", "date": "pas-une-date"}],
    )
    db.add_all([offre_cette_semaine, offre_date_illisible])
    db.commit()
    assert applications_this_week(db) == 1


def test_offres_a_relancer_inclut_la_limite_exacte_du_delai(db, monkeypatch):
    """`changed <= cutoff` : une candidature changée PILE à la limite des 7
    jours doit déjà être signalée, pas seulement au jour suivant. Horloge
    figée : sans elle, le `cutoff` calculé par la fonction (légèrement plus
    tard que celui du test) absorbe l'écart et masque la frontière exacte."""
    maintenant_fixe = local_now()
    monkeypatch.setattr(digest_module, "local_now", lambda: maintenant_fixe)
    cutoff = maintenant_fixe - timedelta(days=RELAUNCH_AFTER_DAYS)
    db.add(Offer(
        fingerprint="fp-pile7", source="test", source_id="pile7", title="Test Manager",
        company="ACME", status="postulee", final_score=80,
        status_history=[{"status": "postulee", "date": cutoff.isoformat(), "par": "u"}],
    ))
    db.commit()
    assert any(o.source_id == "pile7" for o in offers_to_relaunch(db))


def test_next_interviews_fenetre_par_defaut_inclut_pile_21_jours(db, monkeypatch):
    """`jours: int = 21` : un entretien pile au bord de la fenêtre par défaut
    (minuit + 21 jours) doit être inclus, pas seulement les entretiens plus
    proches."""
    maintenant_fixe = local_now().replace(hour=10, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(digest_module, "local_now", lambda: maintenant_fixe)
    minuit = maintenant_fixe.replace(hour=0, minute=0, second=0, microsecond=0)
    dans_la_fenetre = Offer(fingerprint="fp-21j", source="test", source_id="j21",
                            title="Pile 21 jours", company="ACME", final_score=80,
                            interviews=[{"date": (minuit + timedelta(days=21)).isoformat()}])
    hors_fenetre = Offer(fingerprint="fp-22j", source="test", source_id="j22",
                         title="22 jours, hors fenêtre", company="ACME", final_score=80,
                         interviews=[{"date": (minuit + timedelta(days=22)).isoformat()}])
    db.add_all([dans_la_fenetre, hors_fenetre])
    db.commit()
    titres = [e["title"] for e in next_interviews(db)]
    assert "Pile 21 jours" in titres
    assert "22 jours, hors fenêtre" not in titres


def test_next_interviews_tres_matinal_aujourdhui_reste_dans_la_fenetre(db, monkeypatch):
    """`debut = local_now().replace(hour=0, minute=0, second=0, microsecond=0)` :
    un entretien programmé exactement à MINUIT aujourd'hui doit rester dans
    la fenêtre — si l'un des quatre champs n'est pas vraiment ramené à 0,
    `debut` glisse légèrement après cet instant et l'exclut à tort, alors
    que l'horloge réelle est largement plus avancée dans la journée."""
    maintenant_fixe = local_now().replace(hour=15, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(digest_module, "local_now", lambda: maintenant_fixe)
    minuit_pile = maintenant_fixe.replace(hour=0, minute=0, second=0, microsecond=0)
    offer = Offer(fingerprint="fp-matin", source="test", source_id="matin",
                  title="Test Manager", company="ACME", final_score=80,
                  interviews=[{"date": minuit_pile.isoformat()}])
    db.add(offer)
    db.commit()
    a_venir = next_interviews(db)
    assert len(a_venir) == 1
    assert a_venir[0]["aujourdhui"] is True


def test_action_due_limite_exacte_fin_de_journee_incluse(db, monkeypatch):
    """`next_action_date <= end_of_today` (23:59:59) : une action datée pile à
    cette limite doit apparaître dans `actions_due`, pas seulement avant."""
    maintenant_fixe = local_now().replace(hour=10, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(digest_module, "local_now", lambda: maintenant_fixe)
    fin_de_journee = maintenant_fixe.replace(hour=23, minute=59, second=59, microsecond=0)
    # Une microseconde après cette limite ne doit plus apparaître — sans
    # cette seconde offre, un `microsecond=0` muté en `microsecond=1` (fin de
    # journée légèrement plus tardive) resterait indétectable : l'offre
    # incluse serait de toute façon encore <= à la nouvelle limite, élargie.
    db.add_all([
        Offer(fingerprint="fp-finj", source="test", source_id="finj", title="Test Manager",
             company="ACME", final_score=70, next_action_date=fin_de_journee,
             next_action_note="Dernière limite"),
        Offer(fingerprint="fp-apresfinj", source="test", source_id="apresfinj", title="Après la limite",
             company="ACME", final_score=70,
             next_action_date=fin_de_journee + timedelta(microseconds=1),
             next_action_note="Une microseconde trop tard"),
    ])
    db.commit()
    notes = {a["action_note"] for a in actions_due(db)}
    assert "Dernière limite" in notes
    assert "Une microseconde trop tard" not in notes


def test_action_due_overdue_faux_pile_a_minuit_vrai_juste_avant(db, monkeypatch):
    """`next_action_date < start_of_today` : une action datée à MINUIT PILE
    aujourd'hui n'est pas en retard (c'est aujourd'hui) ; une microseconde
    avant, si."""
    maintenant_fixe = local_now().replace(hour=10, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(digest_module, "local_now", lambda: maintenant_fixe)
    minuit = maintenant_fixe.replace(hour=0, minute=0, second=0, microsecond=0)
    db.add_all([
        Offer(fingerprint="fp-minuit", source="test", source_id="minuit", title="Pile minuit",
             company="ACME", final_score=70, next_action_date=minuit, next_action_note="Pile minuit"),
        Offer(fingerprint="fp-avant", source="test", source_id="avant", title="Juste avant",
             company="ACME", final_score=70, next_action_date=minuit - timedelta(microseconds=1),
             next_action_note="Juste avant minuit"),
    ])
    db.commit()
    par_note = {a["action_note"]: a["overdue"] for a in actions_due(db)}
    assert par_note["Pile minuit"] is False
    assert par_note["Juste avant minuit"] is True


def test_daily_focus_sans_arguments_calcule_tout_elle_meme(db):
    """`todo is None`/`gem_list is None`/`relaunch is None` : appelée SANS
    arguments (comme jamais fait par build_digest, qui passe toujours les
    listes déjà calculées), la fonction doit les calculer elle-même plutôt
    que de planter sur un None jamais itérable."""
    db.add(Offer(fingerprint="fp-focus-seul", source="test", source_id="fseul",
                 title="Pépite seule", company="ACME", status="nouvelle", final_score=95))
    db.commit()
    focus = daily_focus(db)
    assert [f["type"] for f in focus] == ["pepite"]


def test_daily_focus_ignore_un_doublon_meme_sans_avoir_atteint_trois(db):
    """`brief["id"] in used` : une MÊME offre à la fois pépite et relance ne
    doit apparaître qu'une fois, même quand il reste de la place dans focus."""
    offre = Offer(fingerprint="fp-double", source="test", source_id="double",
                  title="Offre à la fois pépite et relance", company="ACME",
                  status="postulee", final_score=95,
                  status_history=[{"status": "postulee",
                                   "date": (local_now() - timedelta(days=10)).isoformat(), "par": "u"}])
    db.add(offre)
    db.commit()
    # Même offre utilisée comme pépite ET comme relance : elle ne doit
    # apparaître qu'une fois dans le focus.
    focus = daily_focus(db, todo=[], gem_list=[offre], relaunch=[offre])
    assert len(focus) == 1


def test_daily_focus_note_par_defaut_si_action_sans_note(db):
    db.add(Offer(fingerprint="fp-sansnote", source="test", source_id="sansnote",
                 title="Sans note", company="ACME", final_score=70,
                 next_action_date=local_now() - timedelta(days=1), next_action_note=""))
    db.commit()
    focus = daily_focus(db)
    assert "Action prévue" in focus[0]["label"]


def test_daily_focus_sarrete_pile_a_trois_actions_sans_regarder_le_reste(db):
    """`len(focus) >= 3: return focus` juste après la boucle des actions :
    avec 3 actions déjà échues, ni pépite ni relance ne doivent être ajoutées,
    même si elles existent et qu'il semblerait rester de la place."""
    actions = [
        Offer(fingerprint=f"fp-act3-{i}", source="test", source_id=f"act3-{i}",
             title=f"Action {i}", company="ACME", final_score=70,
             next_action_date=local_now() - timedelta(days=1), next_action_note=f"Note {i}")
        for i in range(3)
    ]
    gem = Offer(fingerprint="fp-gem3", source="test", source_id="gem3", title="Pépite ignorée",
               company="ACME", status="nouvelle", final_score=99)
    db.add_all(actions + [gem])
    db.commit()
    focus = daily_focus(db)
    assert len(focus) == 3
    assert all(f["type"] == "action" for f in focus)


def test_daily_focus_une_seule_pepite_et_une_seule_relance_meme_sll_y_en_a_plus(db):
    """`gem_list[:1]` et `relaunch[:1]` : avec deux pépites et deux relances
    disponibles, une seule de chaque doit atterrir dans le focus."""
    gems_ = [
        Offer(fingerprint=f"fp-g2-{i}", source="test", source_id=f"g2-{i}",
             title=f"Pépite {i}", company="ACME", status="nouvelle", final_score=99 - i)
        for i in range(2)
    ]
    relances_ = [
        Offer(fingerprint=f"fp-r2-{i}", source="test", source_id=f"r2-{i}",
             title=f"Relance {i}", company="ACME", status="postulee", final_score=70 - i)
        for i in range(2)
    ]
    db.add_all(gems_ + relances_)
    db.commit()
    focus = daily_focus(db, todo=[], gem_list=gems_, relaunch=[])
    assert len([f for f in focus if f["type"] == "pepite"]) == 1
    focus2 = daily_focus(db, todo=[], gem_list=[], relaunch=relances_)
    assert len([f for f in focus2 if f["type"] == "relance"]) == 1


def test_daily_focus_push_plafonne_lui_meme_a_trois_sans_attendre_le_retour_de_la_boucle(db):
    """`push()` a SON PROPRE garde (`len(focus) >= 3`, ligne ~206), distinct
    du retour anticipé après la boucle des actions (ligne ~215). Avec
    seulement 2 actions, ce retour anticipé ne se déclenche jamais — c'est
    alors UNIQUEMENT le garde interne de push() qui doit empêcher une 4e
    entrée (ici une relance) de dépasser 3."""
    actions = [
        Offer(fingerprint=f"fp-pc{i}", source="test", source_id=f"pc{i}",
             title=f"Action {i}", company="ACME", final_score=70,
             next_action_date=local_now() - timedelta(days=1), next_action_note=f"n{i}")
        for i in range(2)
    ]
    gem = Offer(fingerprint="fp-pcg", source="test", source_id="pcg", title="Pépite",
               company="ACME", status="nouvelle", final_score=95)
    relance = Offer(fingerprint="fp-pcr", source="test", source_id="pcr", title="Relance refusée",
                    company="ACME", status="postulee", final_score=80)
    db.add_all(actions + [gem, relance])
    db.commit()

    todo = actions_due(db)
    focus = daily_focus(db, todo=todo, gem_list=[gem], relaunch=[relance])
    assert len(focus) == 3
    assert not any(f["type"] == "relance" for f in focus)


def test_daily_focus_objectif_de_secours_seulement_si_moins_de_trois(db):
    """`len(focus) < 3` : avec déjà 3 entrées, le repli « objectif » ne doit
    jamais être tenté ; avec 2, il doit compléter à 3. Le cas « déjà 3 » est
    construit avec 1 action + 1 pépite + 1 relance — jamais 3 actions, ce qui
    déclencherait le retour anticipé de la boucle AVANT même d'atteindre ce
    garde-ci, le rendant invisible."""
    gem = Offer(fingerprint="fp-gfull", source="test", source_id="gfull",
               title="Pépite", company="ACME", status="postulee", final_score=95)
    en_attente = Offer(fingerprint="fp-attente", source="test", source_id="attente",
                       title="En attente", company="ACME", status="a_postuler", final_score=60)
    db.add_all([gem, en_attente])
    db.commit()

    # Une seule pépite, pas d'action ni de relance : focus à 1, le repli complète.
    focus = daily_focus(db, todo=[], gem_list=[gem], relaunch=[])
    assert len(focus) == 2
    assert any(f["type"] == "objectif" for f in focus)

    # 1 action + 1 pépite + 1 relance = déjà 3, sans jamais passer par le
    # retour anticipé de la boucle (1 seule action, 1 < 3) : le repli doit
    # être court-circuité par CE garde précis, pas par un autre.
    action_offre = Offer(fingerprint="fp-act1", source="test", source_id="act1", title="Action seule",
                         company="ACME", final_score=70,
                         next_action_date=local_now() - timedelta(days=1), next_action_note="Seule action")
    relance = Offer(fingerprint="fp-rel1", source="test", source_id="rel1", title="Relance seule",
                    company="ACME", status="postulee", final_score=65)
    db.add_all([action_offre, relance])
    db.commit()
    todo = actions_due(db)
    todo = [a for a in todo if a["title"] == "Action seule"]
    focus_plein = daily_focus(db, todo=todo, gem_list=[gem], relaunch=[relance])
    assert len(focus_plein) == 3
    assert not any(f["type"] == "objectif" for f in focus_plein)


def test_statut_sans_offre_affiche_zero_dans_le_decompte(db):
    db.add(Offer(fingerprint="fp-statut", source="test", source_id="statut",
                 title="Test Manager", company="ACME", status="nouvelle", final_score=50))
    db.commit()
    assert build_digest(db).payload["status_counts"]["refusee"] == 0


def test_rebatir_le_digest_du_meme_jour_met_a_jour_au_lieu_de_dupliquer(db):
    premier = build_digest(db, for_date="2026-01-15")
    second = build_digest(db, for_date="2026-01-15")
    assert premier.id == second.id
    assert db.query(Digest).filter(Digest.date == "2026-01-15").count() == 1


def test_dernier_scan_en_cours_sans_date_de_fin_ne_plante_pas(db):
    from app.models import ScanRun

    db.add(ScanRun(trigger="manuel", status="en_cours"))  # finished_at=None, scan en cours
    db.commit()
    payload = build_digest(db).payload
    assert payload["last_scan"]["finished_at"] is None


def test_digest_html_seuils_de_couleur_a_la_limite_exacte():
    payload = {
        "date": "2026-01-01", "new_count": 0, "status_counts": {}, "total_offers": 0,
        "to_follow": [], "to_follow_total": 0, "to_relaunch": [], "gems": [],
        "todo_today": [], "interviews": [], "focus": [], "weekly": {"goal": 0, "sent": 0},
        "new_offers": [{"final_score": 70, "title": "Pile vert", "company": "C", "location": "L",
                        "url": "u", "source": "s", "contract_type": "CDI"}],
        "top_overall": [{"final_score": 45, "title": "Pile orange", "company": "C", "location": "L",
                         "url": "u", "source": "s", "contract_type": "CDI"}],
    }
    html = digest_html(payload)
    assert "color:#1a7f37" in html  # 70 = vert, pas juste "> 70"
    assert "color:#9a6700" in html  # 45 = orange, pas gris


def test_digest_html_sans_offre_affiche_le_message_francais(db):
    """`counts_html = ... or "Aucune offre pour l'instant"` : sans aucune
    offre, le `or` doit produire le message, pas une ligne vide."""
    html = digest_html(build_digest(db).payload)
    assert "Aucune offre pour l'instant" in html


def test_digest_html_dernier_scan_incomplet_ne_plante_pas():
    """`scan.get('error_count', 0)` / `scan.get('new_count', 0)` : un payload
    minimal (pas construit par build_digest) ne doit pas planter sur les
    clés manquantes."""
    payload = {
        "date": "2026-01-01", "new_count": 0, "status_counts": {}, "total_offers": 0,
        "to_follow": [], "to_follow_total": 0, "to_relaunch": [], "gems": [],
        "todo_today": [], "interviews": [], "focus": [], "weekly": {"goal": 0, "sent": 0},
        "new_offers": [], "top_overall": [], "last_scan": {"finished_at": None},
    }
    html = digest_html(payload)
    assert "0 nouvelle(s) offre(s), 0 erreur(s)" in html


def test_digest_html_total_offres_absent_affiche_zero():
    payload = {
        "date": "2026-01-01", "new_count": 0, "status_counts": {}, "to_follow": [],
        "to_follow_total": 0, "to_relaunch": [], "gems": [], "todo_today": [],
        "interviews": [], "focus": [], "weekly": {"goal": 0, "sent": 0},
        "new_offers": [], "top_overall": [],
    }
    assert "Total : 0 offre" in digest_html(payload)


def test_digest_html_coche_objectif_seulement_si_atteint_et_non_nul():
    base = {
        "date": "2026-01-01", "new_count": 0, "status_counts": {}, "total_offers": 0,
        "to_follow": [], "to_follow_total": 0, "to_relaunch": [], "gems": [],
        "todo_today": [], "interviews": [], "focus": [], "new_offers": [], "top_overall": [],
    }
    # Objectif atteint (sent == goal > 0) : coche.
    assert "✅" in digest_html({**base, "weekly": {"goal": 3, "sent": 3}})
    # Pas encore atteint : pas de coche.
    assert "✅" not in digest_html({**base, "weekly": {"goal": 3, "sent": 2}})
    # Objectif à 0 (> 0 exclut ce cas) : jamais de coche, même « atteint ».
    assert "✅" not in digest_html({**base, "weekly": {"goal": 0, "sent": 0}})
    # Objectif à 1 pile atteint : coche. Un `0` muté en `1` dans `goal > 0`
    # ferait disparaître la coche ici précisément (1 > 1 est faux), alors que
    # l'objectif à 0 ci-dessus ne peut jamais exercer cette partie du test —
    # le paragraphe entier est masqué par ailleurs dès que goal vaut 0.
    assert "✅" in digest_html({**base, "weekly": {"goal": 1, "sent": 1}})


def test_digest_html_todo_sans_note_affiche_le_texte_par_defaut():
    """`a['action_note'] or 'Action prévue'` — propre au rendu email,
    distinct du même repli côté JSON de `daily_focus` (déjà testé)."""
    payload = {
        "date": "2026-01-01", "new_count": 0, "status_counts": {}, "total_offers": 0,
        "to_follow": [], "to_follow_total": 0, "to_relaunch": [], "gems": [],
        "interviews": [], "focus": [], "weekly": {"goal": 0, "sent": 0},
        "new_offers": [], "top_overall": [],
        "todo_today": [{"overdue": False, "action_note": "", "url": "u", "title": "t", "company": "c"}],
    }
    assert "Action prévue" in digest_html(payload)


def test_envoi_digest_sans_smtp_nappelle_jamais_lenvoi(db, monkeypatch):
    monkeypatch.setattr(digest_module, "smtp_configured", lambda: False)
    monkeypatch.setattr(
        digest_module, "send_email",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ne doit pas être appelé")),
    )
    digest = build_digest(db)
    assert send_digest_email(db, digest) is False


def test_envoi_digest_avec_smtp_reussit_et_marque_lenvoi(db, monkeypatch):
    monkeypatch.setattr(digest_module, "smtp_configured", lambda: True)
    envoyes = []
    monkeypatch.setattr(digest_module, "send_email", lambda sujet, corps: envoyes.append(sujet))
    digest = build_digest(db)
    assert send_digest_email(db, digest) is True
    assert digest.email_sent is True
    assert len(envoyes) == 1


def test_envoi_digest_sujet_sans_new_count_ne_plante_pas(db, monkeypatch):
    """`digest.payload.get('new_count', 0)` (ligne du sujet) : isolé de
    `digest_html` (qui a ses propres exigences sur le payload, déjà testées
    ailleurs) pour vérifier uniquement ce défaut-ci."""
    monkeypatch.setattr(digest_module, "smtp_configured", lambda: True)
    sujets = []
    monkeypatch.setattr(digest_module, "send_email", lambda sujet, corps: sujets.append(sujet))
    monkeypatch.setattr(digest_module, "digest_html", lambda payload: "")
    digest = Digest(date="2026-01-02", payload={})  # payload minimal, sans "new_count"
    db.add(digest)
    db.commit()
    assert send_digest_email(db, digest) is True
    assert "0 nouvelle(s)" in sujets[0]


def test_envoi_digest_echec_ne_marque_pas_lenvoi(db, monkeypatch):
    monkeypatch.setattr(digest_module, "smtp_configured", lambda: True)
    monkeypatch.setattr(
        digest_module, "send_email",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("SMTP en panne")),
    )
    digest = build_digest(db)
    assert send_digest_email(db, digest) is False
    assert digest.email_sent is False


def test_resume_semaine_ignore_les_dates_illisibles_sans_planter(db):
    offre = Offer(fingerprint="fp-illisible", source="test", source_id="illisible",
                  title="Test Manager", company="ACME",
                  status_history=[{"status": "postulee", "date": "ceci-n-est-pas-une-date"}])
    db.add(offre)
    db.commit()
    resume = resume_semaine(db)  # ne doit pas lever
    assert resume["candidatures_envoyees"] == 0


def test_resume_semaine_inclut_le_changement_pile_au_debut_de_semaine(db):
    lundi = debut_de_semaine()
    offre = Offer(fingerprint="fp-pilelundi", source="test", source_id="pilelundi",
                  title="Test Manager", company="ACME",
                  status_history=[{"status": "postulee", "date": lundi.isoformat()}])
    db.add(offre)
    db.commit()
    assert resume_semaine(db)["candidatures_envoyees"] == 1


def test_resume_semaine_nouvelles_offres_frontiere_exacte_du_lundi(db):
    """`Offer.collected_at >= debut` : une offre collectée PILE au lundi
    00h00 compte déjà parmi les nouvelles offres de la semaine."""
    lundi = debut_de_semaine()
    db.add(Offer(fingerprint="fp-nvlundi", source="test", source_id="nvlundi",
                 title="Test Manager", company="ACME", collected_at=lundi))
    db.commit()
    assert resume_semaine(db)["nouvelles_offres_collectees"] == 1


def test_resume_semaine_distingue_relances_et_entretiens_en_valeur_exacte(db):
    offre = Offer(fingerprint="fp-actes", source="test", source_id="actes",
                  title="Test Manager", company="ACME",
                  status_history=[{"status": "relancee", "date": local_now().isoformat()}])
    db.add(offre)
    db.commit()
    resume = resume_semaine(db)
    assert resume["relances"] == 1
    assert resume["entretiens_obtenus"] == 0


def test_resume_semaine_objectif_hebdo_reprend_le_vrai_profil(db):
    """`profile.weekly_goal if profile else 5` : si le profil réel vaut 5 (le
    défaut du modèle), ce test ne distingue rien — il faut une valeur
    DIFFÉRENTE de 5 pour prouver que c'est bien LE PROFIL qui est lu."""
    profil = db.get(Profile, 1)
    profil.weekly_goal = 12
    db.commit()
    assert resume_semaine(db)["objectif_hebdo"] == 12


def test_objectif_hebdo_du_digest_reprend_aussi_le_vrai_profil(db):
    profil = db.get(Profile, 1)
    profil.weekly_goal = 9
    db.commit()
    assert build_digest(db).payload["weekly"]["goal"] == 9


def test_objectif_hebdo_replie_sur_5_si_le_profil_nexiste_pas(db):
    """`profile.weekly_goal if profile else 5` : un profil absent (jamais le
    cas en usage réel, mais le code s'en protège) doit retomber sur 5 pile —
    une valeur DIFFÉRENTE du défaut réel du modèle rendrait ce test aveugle
    à un `5` muté en `6`, donc on supprime bien le profil, pas seulement
    son `weekly_goal`."""
    db.query(Profile).filter(Profile.id == 1).delete()
    db.commit()
    assert build_digest(db).payload["weekly"]["goal"] == 5
    assert resume_semaine(db)["objectif_hebdo"] == 5


def test_objectif_hebdo_a_zero_reste_zero_pas_un(db):
    """`(...) or 0` : un objectif explicitement remis à 0 par l'utilisateur
    doit rester 0, jamais retomber sur un défaut non nul."""
    profil = db.get(Profile, 1)
    profil.weekly_goal = 0
    db.commit()
    assert build_digest(db).payload["weekly"]["goal"] == 0
    assert resume_semaine(db)["objectif_hebdo"] == 0


def test_actions_en_retard_du_resume_compte_juste(db):
    actions = [
        Offer(fingerprint=f"fp-retard{i}", source="test", source_id=f"retard{i}",
             title=f"Retard {i}", company="ACME", final_score=60,
             next_action_date=local_now() - timedelta(days=1), next_action_note=f"n{i}")
        for i in range(2)
    ]
    db.add_all(actions)
    db.commit()
    assert resume_semaine(db)["actions_en_retard"] == 2


def test_extraction_texte_principal():
    html = """
    <html><head><script>var x=1;</script><style>.a{}</style></head>
    <body>
      <nav>Accueil Emploi Entreprises Connexion</nav>
      <div class="page">
        <aside>Publicité offres similaires</aside>
        <div class="offre">
          <h1>Test Manager H/F</h1>
          <p>%s</p>
          <p>Vous piloterez la stratégie de test, l'automatisation Selenium et KarateDSL,
          et encadrerez une équipe de testeurs dans un contexte santé ISO 13485.</p>
        </div>
      </div>
      <footer>Mentions légales</footer>
    </body></html>
    """ % ("Description détaillée du poste. " * 30)
    text = extract_main_text(html)
    assert "Test Manager H/F" in text
    assert "Selenium" in text
    assert "Mentions légales" not in text
    assert "var x=1" not in text


def test_header_annonce_preserve_mais_bandeau_site_retire():
    """<header> à l'intérieur de l'annonce = titre du poste (gardé) ; header du body = bandeau (retiré)."""
    html = """
    <html><body>
      <header>Bandeau du site · Connexion · Menu</header>
      <article>
        <header><h1>Responsable QA Lyon</h1></header>
        <p>%s</p>
      </article>
    </body></html>
    """ % ("Contenu détaillé de l'offre avec beaucoup de texte. " * 25)
    text = extract_main_text(html)
    assert "Responsable QA Lyon" in text
    assert "Bandeau du site" not in text


def test_titres_echappes_dans_l_email(db):
    """Un titre contenant « & » ou « <…> » ne doit pas casser l'email."""
    db.add(Offer(
        fingerprint="fp-html", source="france_travail", source_id="html-1",
        title="Test Manager <H/F> R&D", company="ACME & Fils", location="Lyon",
        url="https://exemple.fr/offre?a=1&b=2", final_score=90.0, score=90.0,
        status="nouvelle",
    ))
    db.commit()

    html = digest_html(build_digest(db).payload)
    assert "Test Manager &lt;H/F&gt; R&amp;D" in html
    assert "ACME &amp; Fils" in html
    assert "<H/F>" not in html


def test_le_decor_de_page_n_est_pas_pris_pour_une_offre():
    """Une page rendue côté client (APEC) ne livre que son bandeau cookies.
    Il faisait 417 caractères contre 283 pour le vrai résumé : l'enrichissement
    l'écrasait, et remettait l'avis IA à zéro au passage."""
    from app.services.enrich import ressemble_a_une_offre

    bandeau = (
        "Les informations légales ont changé\nJ'ai pris connaissance des\n"
        "informations légales\nque ce soit les conditions générales d'utilisation, "
        "la Politique de protection de données à caractère personnel ainsi que la "
        "gestion des cookies et je les accepte.\nVous devez accepter les informations "
        "légales\nUne erreur inattendue est survenue. Merci de réessayer ultérieurement."
    )
    assert ressemble_a_une_offre(bandeau) is False


def test_une_vraie_annonce_est_acceptee():
    from app.services.enrich import ressemble_a_une_offre

    annonce = (
        "Test Manager : en un coup d'oeil. Premier éditeur français de cybersécurité, "
        "nous recherchons un Test Manager pour piloter la stratégie de test de nos "
        "produits. Vous animerez une équipe QA, définirez le plan de test, suivrez la "
        "couverture et l'automatisation Selenium et Cypress, et travaillerez avec les "
        "équipes de développement en méthode agile. Environnement CI/CD GitLab, Jira, "
        "tests API. Poste basé à Lyon, télétravail 3 jours par semaine. "
    ) * 2
    assert ressemble_a_une_offre(annonce) is True


def test_une_page_qui_reclame_javascript_n_est_pas_une_offre():
    """Autre visage du même défaut : la page ne parle pas de cookies mais
    réclame JavaScript. Sans ce cas, retirer ces marqueurs de la liste passait
    inaperçu — le message d'attente devenait la description de l'offre."""
    from app.services.enrich import ressemble_a_une_offre

    ecran = ("Cette page nécessite JavaScript pour fonctionner correctement. "
             "Veuillez activer JavaScript dans les paramètres de votre navigateur, "
             "puis recharger la page pour consulter cette annonce. " * 3)
    assert ressemble_a_une_offre(ecran) is False


def test_une_annonce_qui_mentionne_les_conditions_generales_en_bas_reste_acceptee():
    """Le décor se reconnaît EN TÊTE : on ne rejette pas une vraie annonce
    parce qu'elle cite les conditions générales dans son pied de page."""
    from app.services.enrich import ressemble_a_une_offre

    annonce = ("Nous recherchons un Test Manager expérimenté pour piloter notre "
               "stratégie qualité. " * 12) + "\nMentions et conditions générales d'utilisation."
    assert ressemble_a_une_offre(annonce) is True


# --- La route d'enrichissement, sur de vraies requêtes HTTP -------------------
#
# Le chemin complet (route → fetch_full_description → httpx → extract_main_text
# → garde-fou) doit être vérifiable sans dépendre d'apec.fr. On sert donc les
# deux pages depuis un VRAI serveur HTTP local : rien n'est bouchonné, et le
# résultat ne dépend ni du réseau ni de l'humeur d'un site tiers.
#
# Bouchonner `fetch_full_description`, c'est court-circuiter précisément la
# fonction qui portait le défaut — c'est ce que faisait l'ancien test, et c'est
# pour ça qu'il n'a rien vu.

# Bandeau réel de l'APEC : 417 caractères, PLUS LONGS que le résumé de 283
# caractères fourni par son API. Le garde « déjà aussi complet » ne protège donc
# pas — c'est tout le sujet.
BANDEAU_APEC = (
    "J'ai pris connaissance des informations légales, que ce soit les conditions "
    "générales d'utilisation, la Politique de protection de données à caractère "
    "personnel ainsi que la gestion des cookies, et je les accepte. Vous devez "
    "accepter les informations légales pour continuer votre navigation sur le site. "
    "Une erreur inattendue est survenue. Merci de réessayer ultérieurement. "
    "Veuillez activer JavaScript dans votre navigateur pour accéder à cette page."
)
ANNONCE_COMPLETE = (
    "Vous piloterez la stratégie de test d'une plateforme critique : rédaction du "
    "plan de test, animation de l'équipe QA, automatisation Selenium et Cypress, "
    "intégration continue, suivi des anomalies sous Jira. " * 8
)
# 283 caractères : la longueur exacte à laquelle l'API de l'APEC tronque son résumé.
RESUME_TRONQUE = "Nous recherchons un Lead QA pour piloter la stratégie de test. " * 4 + "Fin."

PAGES = {
    "/bandeau": f"<html><body><div><p>{BANDEAU_APEC}</p></div></body></html>",
    "/annonce": f"<html><body><article><p>{ANNONCE_COMPLETE}</p></article></body></html>",
}


@pytest.fixture(scope="module")
def serveur_de_pages():
    """Un vrai serveur HTTP local, le temps du module."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            corps = PAGES.get(self.path, "<html><body>introuvable</body></html>").encode("utf-8")
            self.send_response(200 if self.path in PAGES else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *_):
            pass                                  # pas de bruit dans la sortie des tests

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _offre_enrichie(db, url, description):
    offre = Offer(
        fingerprint=f"fp-{url[-8:]}", source="apec", source_id=url[-8:],
        title="Lead QA", company="O2MAX", description=description, url=url,
        score=60, final_score=45, ai_score=30.0, ai_reason="Avis existant.",
    )
    db.add(offre)
    db.commit()
    return offre


def _enrichir(db, offre):
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app
    from app.routers.offers import get_db

    def override_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        return TestClient(fastapi_app).post(f"/api/offers/{offre.id}/enrich")
    finally:
        fastapi_app.dependency_overrides.clear()


def test_le_bandeau_de_cookies_ne_remplace_pas_la_description(db, serveur_de_pages):
    """Sans le garde-fou, la description réelle était remplacée par le bandeau
    ET l'avis IA repartait à zéro — deux pertes irrécupérables, l'utilisateur
    n'ayant aucun moyen de revenir en arrière."""
    offre = _offre_enrichie(db, f"{serveur_de_pages}/bandeau", RESUME_TRONQUE)

    reponse = _enrichir(db, offre)

    assert reponse.status_code == 502, reponse.text
    db.refresh(offre)
    assert offre.description == RESUME_TRONQUE
    assert offre.ai_score == 30.0
    assert offre.ai_reason == "Avis existant."


def test_une_vraie_annonce_remplace_la_description_et_remet_l_avis_ia_a_zero(db, serveur_de_pages):
    """L'autre moitié du contrat : le garde-fou ne doit pas tout refuser, et
    l'avis IA portait sur l'ancien extrait — il est recalculé, pas conservé."""
    offre = _offre_enrichie(db, f"{serveur_de_pages}/annonce", "Extrait court.")

    reponse = _enrichir(db, offre)

    assert reponse.status_code == 200, reponse.text
    donnees = reponse.json()
    assert "stratégie de test" in donnees["description"]
    assert donnees["ai_score"] is None
    assert donnees["ai_reason"] == ""
    assert donnees["final_score"] == donnees["score"]


def test_une_page_introuvable_laisse_l_offre_intacte(db, serveur_de_pages):
    """Un 404 sur la page d'origine ne doit rien abîmer non plus."""
    offre = _offre_enrichie(db, f"{serveur_de_pages}/disparue", RESUME_TRONQUE)

    assert _enrichir(db, offre).status_code == 502
    db.refresh(offre)
    assert offre.description == RESUME_TRONQUE
    assert offre.ai_score == 30.0
