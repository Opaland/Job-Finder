"""Sprint 25 : compétences les plus demandées par le marché."""
from app.models import Offer, Profile
from app.services.marche import competences_demandees


def _offre(db, id_source, titre, description):
    db.add(Offer(fingerprint=f"fp-{id_source}", source="manuelle", source_id=id_source,
                 title=titre, company="ACME", description=description, final_score=70.0))
    db.commit()


def test_classement_des_competences(client, db):
    _offre(db, "m1", "QA Lead", "Automatisation Selenium et Playwright, CI/CD GitLab.")
    _offre(db, "m2", "Test Manager", "Stratégie de test, Selenium, Jira.")
    _offre(db, "m3", "Testeur", "Tests manuels avec Jira.")

    resultat = competences_demandees(db)
    assert resultat["total_offres"] == 3
    assert resultat["assez_de_donnees"] is True
    classement = {c["competence"]: c for c in resultat["competences"]}
    assert classement["selenium"]["offres"] == 2
    assert classement["jira"]["offres"] == 2
    assert classement["playwright"]["offres"] == 1
    # Le classement est trié par nombre d'offres décroissant.
    nombres = [c["offres"] for c in resultat["competences"]]
    assert nombres == sorted(nombres, reverse=True)


def test_part_en_pourcentage(client, db):
    _offre(db, "m1", "QA", "Selenium partout.")
    _offre(db, "m2", "QA", "Rien de particulier.")
    selenium = next(c for c in competences_demandees(db)["competences"] if c["competence"] == "selenium")
    assert selenium["part"] == 50


def test_competences_du_cv_reperees(client, db):
    profile = db.get(Profile, 1)
    profile.skills = ["selenium", "jira"]
    db.commit()
    _offre(db, "m1", "QA Lead", "Selenium, Playwright et Jira.")

    resultat = competences_demandees(db)
    classement = {c["competence"]: c for c in resultat["competences"]}
    assert classement["selenium"]["dans_le_cv"] is True
    assert classement["playwright"]["dans_le_cv"] is False
    # Les manquantes sont exactement celles absentes du CV.
    assert "playwright" in [c["competence"] for c in resultat["manquantes"]]
    assert "selenium" not in [c["competence"] for c in resultat["manquantes"]]


def test_dans_le_cv_reconnait_une_sous_chaine_dans_les_deux_sens(client, db):
    """`competence in s or s in competence` : « java » cité dans une offre
    doit être marqué « déjà au CV » si le CV contient « javascript » — la
    sous-chaîne joue dans CE sens-là aussi, pas seulement l'inverse."""
    profile = db.get(Profile, 1)
    profile.skills = ["javascript"]
    db.commit()
    _offre(db, "m-java", "Développeur", "Poste principalement en java, avec un peu de k6.")
    classement = {c["competence"]: c for c in competences_demandees(db)["competences"]}
    assert classement["java"]["dans_le_cv"] is True
    assert classement["k6"]["dans_le_cv"] is False


def test_base_vide_ne_casse_pas(client, db):
    resultat = competences_demandees(db)
    assert resultat["total_offres"] == 0
    assert resultat["assez_de_donnees"] is False
    assert resultat["competences"] == []


def test_route_api(client, db):
    _offre(db, "m1", "QA Lead", "Playwright et Cypress.")
    resp = client.get("/api/market/skills?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["competences"]) <= 5


# --- Sprint 26 : salaires et entreprises ------------------------------------

def test_lecture_des_salaires_formats_reels():
    from app.services.marche import montants_annuels
    assert montants_annuels("45 000 - 55 000 € / an") == [45000, 55000]
    assert montants_annuels("45K€ à 60K€") == [45000, 60000]
    assert montants_annuels("Mensuel de 3500,00 Euros à 4200,00 Euros") == [42000, 50400]
    assert montants_annuels("Selon profil") == []
    assert montants_annuels("2 ans d'expérience") == []   # aucune unité monétaire


def test_montants_aberrants_ecartes():
    from app.services.marche import montants_annuels
    assert montants_annuels("1 200 € par an") == []        # sous le plancher
    assert montants_annuels("900 000 € / an") == []        # au-dessus du plafond


def test_qui_recrute_et_mediane(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    for i, (entreprise, salaire, score) in enumerate([
        ("ACME", "45 000 - 55 000 € / an", 80.0),
        ("ACME", "50 000 € / an", 70.0),
        ("Bêta", "", 60.0),
    ]):
        db.add(Offer(fingerprint=f"fp-s{i}", source="manuelle", source_id=f"s{i}",
                     title="Test Manager", company=entreprise, salary_text=salaire, final_score=score))
    db.commit()

    resultat = qui_recrute(db)
    premiere = resultat["entreprises"][0]
    assert premiere["entreprise"] == "ACME"
    assert premiere["offres"] == 2
    assert premiere["score_moyen"] == 75.0
    assert resultat["offres_avec_salaire"] == 2
    salaires = resultat["salaires"][0]
    assert salaires["minimum"] == 45000 and salaires["maximum"] == 55000
    assert salaires["median"] == 50000


def test_offre_close_ne_compte_plus_comme_recruteur_actif(client, db):
    """Issue #13 : une entreprise restait comptée comme recruteur actif même
    si son unique offre avait été refusée ou fermée depuis longtemps."""
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add(Offer(fingerprint="fp-close", source="manuelle", source_id="close",
                 title="Test Manager", company="Entreprise Close", final_score=50.0,
                 status="refusee"))
    db.commit()
    assert qui_recrute(db)["entreprises"] == []


def test_salaire_sur_peu_d_offres_est_signale_non_fiable(client, db):
    """Issue #13 : une médiane sur 1-2 offres n'est pas une tendance de marché."""
    from app.models import Offer
    from app.services.marche import MIN_OFFRES, qui_recrute
    db.add(Offer(fingerprint="fp-peu", source="manuelle", source_id="peu",
                 title="Expert QA", company="ACME", salary_text="50 000 € / an", final_score=70.0))
    db.commit()
    resultat = qui_recrute(db)
    assert resultat["salaires_fiables_a_partir_de"] == MIN_OFFRES
    assert resultat["salaires"][0]["offres"] == 1
    assert resultat["salaires"][0]["fiable"] is False


def test_entreprise_vide_regroupee(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add(Offer(fingerprint="fp-x", source="manuelle", source_id="x", title="QA", company="", final_score=50.0))
    db.commit()
    assert qui_recrute(db)["entreprises"][0]["entreprise"] == "Entreprise non précisée"


# --- Sprint 27 : manques récurrents repérés par l'IA ------------------------

def test_manques_recurrents(client, db):
    from app.models import Offer, Profile
    from app.services.marche import manques_recurrents
    profile = db.get(Profile, 1)
    profile.skills = ["selenium"]
    db.commit()
    for i, analyse in enumerate([
        "Le CV couvre Selenium mais Playwright et k6 manquent.",
        "Il faudrait ajouter Playwright pour ce poste.",
        None,
    ]):
        db.add(Offer(fingerprint=f"fp-g{i}", source="manuelle", source_id=f"g{i}",
                     title="QA", company="ACME", final_score=70.0, gap_analysis=analyse))
    db.commit()

    resultat = manques_recurrents(db)
    assert resultat["analyses"] == 2                    # l'offre sans analyse est ignorée
    manques = {m["competence"]: m["citee_dans"] for m in resultat["manques"]}
    assert manques["playwright"] == 2
    assert manques["k6"] == 1
    assert "selenium" not in manques                    # déjà au CV : pas un manque


# --- Sprint 28 : fraîcheur et annonces fantômes -----------------------------

def test_tranches_de_fraicheur_et_fantomes(client, db):
    from datetime import timedelta

    from app.models import Offer, local_now
    from app.services.marche import fraicheur
    maintenant = local_now()
    cas = [
        ("f1", maintenant - timedelta(days=2), True, "nouvelle"),
        ("f2", maintenant - timedelta(days=20), True, "vue"),
        ("f3", maintenant - timedelta(days=45), True, "nouvelle"),
        ("f4", maintenant - timedelta(days=120), True, "nouvelle"),   # fantôme
        ("f5", maintenant - timedelta(days=200), False, "nouvelle"),  # ancienne mais hors ligne
        ("f6", None, True, "nouvelle"),
        ("f7", maintenant - timedelta(days=300), True, "refusee"),    # close : ignorée
    ]
    for source_id, publiee, en_ligne, statut in cas:
        db.add(Offer(fingerprint=f"fp-{source_id}", source="manuelle", source_id=source_id,
                     title="QA", company="ACME", final_score=60.0,
                     published_at=publiee, still_online=en_ligne, status=statut))
    db.commit()

    resultat = fraicheur(db)
    tranches = {t["tranche"]: t["offres"] for t in resultat["tranches"]}
    assert tranches["0-7"] == 1
    assert tranches["8-30"] == 1
    assert tranches["31-60"] == 1
    assert tranches["60+"] == 2          # f4 et f5
    assert tranches["inconnue"] == 1
    # Seule une offre ancienne ET toujours en ligne est signalée fantôme.
    fantomes = [f["source_id"] if "source_id" in f else f["jours"] for f in resultat["fantomes"]]
    assert len(resultat["fantomes"]) == 1
    assert resultat["fantomes"][0]["jours"] >= 120


def test_tranches_de_fraicheur_a_leurs_frontieres_exactes(client, db):
    """Les trois frontières (7/8, 30/31, 60/61 jours) n'étaient testées qu'au
    large (2, 20, 45, 120, 200 j) — jamais pile dessus. Le seuil "fantôme" était
    en plus codé en dur (60) indépendamment de FANTOME_APRES_JOURS, le champ
    `seuil_fantome_jours` affiché pouvait donc mentir sans qu'aucun test ne le
    voie si la constante seule changeait."""
    from datetime import timedelta

    from app.models import Offer, local_now
    from app.services.marche import FANTOME_APRES_JOURS, fraicheur
    maintenant = local_now()
    cas = [
        ("p7", 7), ("p8", 8), ("p30", 30), ("p31", 31),
        (f"p{FANTOME_APRES_JOURS}", FANTOME_APRES_JOURS),
        (f"p{FANTOME_APRES_JOURS + 1}", FANTOME_APRES_JOURS + 1),
    ]
    for source_id, age in cas:
        db.add(Offer(fingerprint=f"fp-{source_id}", source="manuelle", source_id=source_id,
                     title="QA", company="ACME", final_score=60.0,
                     published_at=maintenant - timedelta(days=age), status="nouvelle"))
    db.commit()

    tranches = {t["tranche"]: t["offres"] for t in fraicheur(db)["tranches"]}
    assert tranches["0-7"] == 1       # p7
    assert tranches["8-30"] == 2      # p8, p30
    assert tranches["31-60"] == 2     # p31, p{FANTOME_APRES_JOURS}
    assert tranches["60+"] == 1       # p{FANTOME_APRES_JOURS + 1}


# --- Sprint 61 : trous relevés par mutation testing ---------------------------

def test_le_plus_long_mot_de_la_taxonomie_est_cherche_dabord(client, db):
    """`sorted(SKILL_TAXONOMY, key=len, reverse=True)` : sans le tri du plus
    long au plus court, « javascript » se ferait happer par « java » (préfixe
    de la taxonomie) et ne serait jamais reconnu pour lui-même."""
    _offre(db, "m-js", "Développeur", "Projet entièrement en javascript, migré depuis PHP.")
    classement = {c["competence"]: c["offres"] for c in competences_demandees(db)["competences"]}
    assert classement.get("javascript") == 1
    assert "java" not in classement


def test_classement_plafonne_a_25_competences_par_defaut(client, db):
    from app.services.cv_parser import SKILL_TAXONOMY
    choisies = list(SKILL_TAXONOMY)[:26]
    assert len(choisies) == 26
    _offre(db, "m-26", "QA", " ".join(choisies))
    assert len(competences_demandees(db)["competences"]) == 25


def test_score_pile_au_plancher_est_compte_juste_sous_pas(client, db):
    from app.models import Offer
    from app.services.marche import SCORE_PLANCHER
    assert SCORE_PLANCHER == 25  # la valeur réelle, pas seulement son effet de bord
    db.add_all([
        Offer(fingerprint="fp-plancher", source="manuelle", source_id="plancher",
             title="QA", company="ACME", description="Selenium partout.", final_score=SCORE_PLANCHER),
        Offer(fingerprint="fp-sousplancher", source="manuelle", source_id="sousplancher",
             title="QA", company="ACME", description="Selenium partout.", final_score=SCORE_PLANCHER - 1),
    ])
    db.commit()
    assert competences_demandees(db)["total_offres"] == 1


def test_titre_vide_ne_plante_pas_le_classement(client, db):
    """`titre or ''` : `title` est NOT NULL en base (jamais None réellement),
    et `description` a un défaut Python absorbant un `None` explicite —
    seule l'alternative restante (titre vide "") est atteignable, mais elle
    ne distingue pas `or` de `and` ("" des deux côtés). Ce `or`-ci est donc
    un mutant équivalent, vérifié à la main ; régression gardée quand même."""
    from app.models import Offer
    db.add(Offer(fingerprint="fp-sanstitre", source="manuelle", source_id="sanstitre",
                 title="", company="ACME", description="Selenium et Cypress.", final_score=70.0))
    db.commit()
    assert "selenium" in {c["competence"] for c in competences_demandees(db)["competences"]}


def test_part_en_pourcentage_sans_coincidence_darrondi(client, db):
    """`round(100 * nombre / total)` : un tiers (33 %) distingue un `100`
    muté en `101` (33,67 → 34), contrairement à une moitié déjà testée
    ailleurs (50,5 arrondit à 50 dans les deux cas — round-half-to-even)."""
    _offre(db, "m1", "QA", "Selenium.")
    _offre(db, "m2", "QA", "Rien.")
    _offre(db, "m3", "QA", "Rien non plus.")
    selenium = next(c for c in competences_demandees(db)["competences"] if c["competence"] == "selenium")
    assert selenium["part"] == 33


def test_classement_egalite_triee_par_ordre_alphabetique(client, db):
    """`sorted(..., key=lambda kv: (-kv[1], kv[0]))` : à nombre d'offres
    égal, le tri retombe sur l'ordre alphabétique — pas un second tri par
    nombre (redondant, donc muet sur l'ordre réel). `compteur` est construit
    à partir d'un `set` (ordre d'itération randomisé par processus) : avec
    SEULEMENT deux compétences à égalité, un tri cassé reste indétectable
    une fois sur deux (ordre déjà "bon" par hasard). Six compétences
    rendent la coïncidence négligeable (1 chance sur 6! ≈ 720)."""
    from app.services.cv_parser import SKILL_TAXONOMY
    choisies = sorted(SKILL_TAXONOMY, key=len)[:6]  # 6 compétences courtes, toutes citées 1 fois
    _offre(db, "m1", "QA", " ".join(choisies))
    competences = [c["competence"] for c in competences_demandees(db)["competences"]
                  if c["competence"] in choisies]
    assert competences == sorted(competences)


def test_manquantes_plafonnees_a_dix(client, db):
    from app.models import Offer
    from app.services.cv_parser import SKILL_TAXONOMY
    choisies = list(SKILL_TAXONOMY)[:11]
    db.add(Offer(fingerprint="fp-11manques", source="manuelle", source_id="m11",
                 title="QA", company="ACME", description=" ".join(choisies), final_score=70.0))
    db.commit()
    assert len(competences_demandees(db)["manquantes"]) == 10


def test_montants_bornes_de_plausibilite_inclusives():
    from app.services.marche import montants_annuels
    assert montants_annuels("15 000 € / an") == [15000]     # pile le plancher : retenu
    assert montants_annuels("14 999 € / an") == []          # juste en dessous : écarté
    assert montants_annuels("250 000 € / an") == [250000]   # pile le plafond : retenu
    assert montants_annuels("250 001 € / an") == []         # juste au-dessus : écarté


def test_montants_annuels_texte_vide_ou_sans_montant():
    from app.services.marche import montants_annuels
    assert montants_annuels("") == []


def test_dernier_nombre_sans_unite_nest_jamais_recherche_hors_liste():
    """`rang + 1 < len(trouves)` : un nombre sans unité en DERNIÈRE position
    (pas de borne suivante à qui emprunter une unité) ne doit ni planter, ni
    être pris pour un salaire."""
    from app.services.marche import montants_annuels
    assert montants_annuels("45 K€ pour un poste de 39h hebdomadaires") == [45000]


def test_separateur_de_fourchette_regarde_le_vrai_texte_entre_deux_nombres():
    """`texte[correspondance.end(1):suivant.start(1)]` : si ce calcul utilisait
    la mauvaise référence de groupe, la tranche de texte inspectée s'effondre
    en chaîne vide — qui satisfait toujours le motif de séparateur (il
    accepte l'absence de séparateur). Un nombre séparé par un texte qui n'a
    RIEN d'une fourchette (« du lundi au vendredi ») emprunterait alors à
    tort l'unité du nombre suivant."""
    from app.services.marche import montants_annuels
    assert montants_annuels("39h du lundi au vendredi, 45 K€ de budget formation") == [45000]


def test_conversion_k_euros_a_la_limite_exacte_de_1000():
    """`valeur < 1000` : sous 1000, « K€ » est bien un multiplicateur (16 K€ =
    16 000 €) ; à 1000 pile, la valeur est déjà en euros bruts — un second
    ×1000 la rendrait absurde (1 000 000 €), elle reste donc 1000 € telle
    quelle (et sort du calcul, bien trop bas pour un salaire plausible).
    Les frontières exactes de `< 1000` (opérateur et littéral) sont, elles,
    des mutants équivalents vérifiés à la main : à 1000 pile avec « K€ »,
    multiplier ou non donne 1000 (trop bas) ou 1 000 000 (trop haut) — les
    deux sortent de toute façon des bornes de plausibilité."""
    from app.services.marche import montants_annuels
    assert montants_annuels("16 K€ / an") == [16000]
    assert montants_annuels("1000 K€ / an") == []
    # `and` muté en `or` : un montant SANS « K » (donc sans raison d'être
    # ×1000) mais < 1000 ne doit pas être multiplié pour autant — sinon
    # « 50 € » (un acompte, une prime...) deviendrait un salaire de 50 000 €
    # (vérifié à la main : « 500 € » retombait hors plafond dans les deux
    # cas et ne distinguait rien).
    assert montants_annuels("50 € / an") == []


def test_conversion_mensuelle_a_la_limite_exacte_du_plancher():
    """`mensuel and valeur < SALAIRE_MIN` : pile au plancher (15 000), le
    nombre lu est déjà un montant annuel plausible en soi — pas de ×12
    (limite connue et assumée du code : un vrai 15 000 €/mois resterait
    compté comme 15 000 €/an). Juste sous le plancher, le ×12 s'applique."""
    from app.services.marche import montants_annuels
    assert montants_annuels("15000 € par mois") == [15000]          # pile au plancher : pas de ×12
    assert montants_annuels("14999 € par mois") == [179988]         # juste sous : ×12 appliqué


def test_mediane_sur_nombre_impair_prend_bien_lelement_du_milieu():
    from app.services.marche import _mediane
    assert _mediane([50, 10, 100, 20, 40]) == 40  # trié : 10,20,40,50,100 → milieu = 40


def test_mediane_sur_nombre_pair_moyenne_les_deux_elements_du_milieu():
    from app.services.marche import _mediane
    assert _mediane([10, 20, 30, 41]) == 25  # (20 + 30) // 2


def test_score_absent_compte_comme_zero_pas_comme_exclu(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add(Offer(fingerprint="fp-sansscore", source="manuelle", source_id="sansscore",
                 title="QA", company="ACME", final_score=None))
    db.commit()
    resultat = qui_recrute(db)
    assert resultat["entreprises"][0]["score_moyen"] == 0.0


def test_intitule_reflete_le_vrai_titre_pas_toujours_autre(client, db):
    """`canonical_title(titre or "") or "autre"` : un `or` devenu `and` sur
    la PREMIÈRE moitié (`titre or ""`) ferait toujours retomber `cle` sur ""
    puis "autre", QUEL QUE SOIT le titre réel — jamais remarqué si aucun
    test ne regarde `intitule` pour un titre normal, non vide."""
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add(Offer(fingerprint="fp-titrereel", source="manuelle", source_id="titrereel",
                 title="Test Manager", company="A", salary_text="45 000 € / an", final_score=70.0))
    db.commit()
    assert qui_recrute(db)["salaires"][0]["intitule"] == "test manager"


def test_intitule_sans_forme_canonique_se_replie_sur_autre(client, db):
    """Second repli de la même ligne : un titre réel mais sans forme
    canonique (« H/F » seul) doit retomber sur "autre", pas planter."""
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add(Offer(fingerprint="fp-titrenoncanon", source="manuelle", source_id="titrenoncanon",
                 title="H/F", company="B", salary_text="46 000 € / an", final_score=70.0))
    db.commit()
    assert qui_recrute(db)["salaires"][0]["intitule"] == "autre"


def test_score_moyen_arrondi_a_une_decimale_pas_a_lentier(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    db.add_all([
        Offer(fingerprint="fp-sm1", source="manuelle", source_id="sm1",
             title="QA", company="ACME", final_score=70.0),
        Offer(fingerprint="fp-sm2", source="manuelle", source_id="sm2",
             title="QA", company="ACME", final_score=71.0),
        Offer(fingerprint="fp-sm3", source="manuelle", source_id="sm3",
             title="QA", company="ACME", final_score=73.0),
    ])
    db.commit()
    assert qui_recrute(db)["entreprises"][0]["score_moyen"] == 71.3


def test_salaire_fiable_pile_au_seuil_de_min_offres(client, db):
    from app.models import Offer
    from app.services.marche import MIN_OFFRES, qui_recrute
    for i in range(MIN_OFFRES):
        db.add(Offer(fingerprint=f"fp-fiable{i}", source="manuelle", source_id=f"fiable{i}",
                     title="Expert QA", company="ACME", salary_text="50 000 € / an", final_score=70.0))
    db.commit()
    assert qui_recrute(db)["salaires"][0]["fiable"] is True


def test_qui_recrute_plafonne_a_20_entreprises_par_defaut(client, db):
    from app.models import Offer
    from app.services.marche import qui_recrute
    for i in range(21):
        db.add(Offer(fingerprint=f"fp-ent{i}", source="manuelle", source_id=f"ent{i}",
                     title="QA", company=f"Entreprise {i}", final_score=70.0))
    db.commit()
    assert len(qui_recrute(db)["entreprises"]) == 20


def test_manques_recurrents_plafonne_a_15_par_defaut(client, db):
    from app.models import Offer, Profile
    from app.services.cv_parser import SKILL_TAXONOMY
    from app.services.marche import manques_recurrents
    db.get(Profile, 1).skills = []
    choisies = list(SKILL_TAXONOMY)[:16]
    db.add(Offer(fingerprint="fp-manques16", source="manuelle", source_id="manques16",
                 title="QA", company="ACME", final_score=70.0,
                 gap_analysis="Manquent : " + ", ".join(choisies)))
    db.commit()
    assert len(manques_recurrents(db)["manques"]) == 15


def test_manques_recurrents_egalite_triee_par_ordre_alphabetique(client, db):
    """Même piège que pour `competences_demandees` (set à ordre randomisé) :
    six compétences à égalité plutôt que deux, pour que la coïncidence d'un
    ordre déjà "bon" malgré un tri cassé devienne négligeable."""
    from app.models import Offer, Profile
    from app.services.cv_parser import SKILL_TAXONOMY
    from app.services.marche import manques_recurrents
    db.get(Profile, 1).skills = []
    choisies = sorted(SKILL_TAXONOMY, key=len)[:6]
    db.add(Offer(fingerprint="fp-manquesalpha", source="manuelle", source_id="manquesalpha",
                 title="QA", company="ACME", final_score=70.0,
                 gap_analysis="Manquent : " + ", ".join(choisies)))
    db.commit()
    competences = [m["competence"] for m in manques_recurrents(db)["manques"]
                  if m["competence"] in choisies]
    assert competences == sorted(competences)


def test_manques_recurrents_ignore_une_competence_sous_chaine_dune_competence_du_cv(client, db):
    """`competence in s or s in competence` : « java » est une sous-chaîne de
    « javascript ». Si le CV a « javascript », « java » cité dans une analyse
    ne doit pas être signalé comme un manque — l'OR doit tenir dans les deux
    sens, pas seulement un."""
    from app.models import Offer, Profile
    from app.services.marche import manques_recurrents
    profile = db.get(Profile, 1)
    profile.skills = ["javascript"]
    db.commit()
    db.add(Offer(fingerprint="fp-javamanque", source="manuelle", source_id="javamanque",
                 title="QA", company="ACME", final_score=70.0,
                 gap_analysis="Le profil ne connaît pas le java ni le k6."))
    db.commit()
    manques = {m["competence"] for m in manques_recurrents(db)["manques"]}
    assert "java" not in manques
    assert "k6" in manques


def test_fantome_apres_jours_vaut_bien_60():
    from app.services.marche import FANTOME_APRES_JOURS
    assert FANTOME_APRES_JOURS == 60


def test_fraicheur_plafonne_les_fantomes_a_20_par_defaut(client, db):
    from datetime import timedelta

    from app.models import Offer, local_now
    from app.services.marche import fraicheur
    maintenant = local_now()
    for i in range(21):
        db.add(Offer(fingerprint=f"fp-fantome{i}", source="manuelle", source_id=f"fantome{i}",
                     title="QA", company="ACME", final_score=60.0,
                     published_at=maintenant - timedelta(days=100 + i), still_online=True))
    db.commit()
    assert len(fraicheur(db)["fantomes"]) == 20
