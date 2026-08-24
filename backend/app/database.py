import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger("jobfinder.db")


class Base(DeclarativeBase):
    pass


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


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
