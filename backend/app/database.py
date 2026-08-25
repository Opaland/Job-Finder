import logging

from sqlalchemy import JSON, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger("jobfinder.db")


class Base(DeclarativeBase):
    pass


def _json_vide(column) -> str | None:
    """« [] » ou « {} » selon le défaut Python de la colonne JSON, sinon None.

    SQLAlchemy encapsule les défauts appelables (`default=list`) : on évalue
    donc le défaut au lieu de comparer la fonction, qui n'est plus `list`.
    """
    if not isinstance(column.type, JSON) or column.default is None:
        return None
    arg = column.default.arg
    if callable(arg):
        try:
            valeur = arg(None)          # forme encapsulée : callable(contexte)
        except TypeError:
            valeur = arg()
    else:
        valeur = arg
    if isinstance(valeur, list):
        return "[]"
    if isinstance(valeur, dict):
        return "{}"
    return None


def ensure_schema(target_engine) -> None:
    """Migration légère : ajoute à la base existante les colonnes apparues dans les modèles.

    `create_all` crée les tables manquantes mais ne modifie jamais une table
    existante ; ce complément préserve les données de l'utilisateur lors des
    mises à jour de l'application (SQLite accepte ALTER TABLE ... ADD COLUMN).
    """
    from . import models  # noqa: F401 — enregistre les tables dans Base.metadata

    Base.metadata.create_all(target_engine)
    inspector = inspect(target_engine)
    with target_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(target_engine.dialect)
                default_clause = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    arg = column.default.arg
                    if isinstance(arg, bool):
                        default_clause = f" DEFAULT {1 if arg else 0}"
                    elif isinstance(arg, (int, float)):
                        default_clause = f" DEFAULT {arg}"
                    elif isinstance(arg, str):
                        default_clause = " DEFAULT '{}'".format(arg.replace("'", "''"))
                # Colonnes JSON (list/dict) : sans valeur, les lignes existantes
                # recevraient NULL et l'API les rejetterait au premier affichage.
                elif (vide := _json_vide(column)) is not None:
                    default_clause = f" DEFAULT '{vide}'"
                if not column.nullable and not default_clause:
                    logger.warning(
                        "Migration : %s.%s est NOT NULL sans défaut scalaire — "
                        "les lignes existantes recevront NULL",
                        table.name, column.name,
                    )
                conn.execute(
                    text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}{default_clause}")
                )
                logger.info("Migration : colonne %s.%s ajoutée", table.name, column.name)

        # Rattrapage : toute colonne JSON à NULL est remise à sa valeur vide.
        # Le balayage porte sur l'ensemble des colonnes JSON, pas seulement celles
        # ajoutées à l'instant : une version antérieure a pu en laisser à NULL, et
        # les schémas de réponse les refusent (erreur au premier affichage). Sur
        # une base personnelle, ces quelques UPDATE sont imperceptibles.
        reparees = 0
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                vide = _json_vide(column)
                if vide is None:
                    continue
                resultat = conn.execute(text(
                    f"UPDATE {table.name} SET {column.name} = '{vide}' WHERE {column.name} IS NULL"
                ))
                reparees += resultat.rowcount or 0
        if reparees:
            logger.info("Migration : %d valeur(s) JSON vide(s) restaurée(s)", reparees)


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    # timeout : l'appli et la CLI (scan.bat) peuvent écrire en même temps —
    # mieux vaut attendre le verrou que renvoyer « database is locked ».
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _reglages_sqlite(connexion, _record):
    """WAL : lecture et écriture concurrentes (interface ouverte pendant un scan)."""
    curseur = connexion.cursor()
    curseur.execute("PRAGMA journal_mode=WAL")
    curseur.execute("PRAGMA busy_timeout=30000")
    curseur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
