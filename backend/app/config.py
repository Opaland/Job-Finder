"""Configuration de l'application, chargée depuis le fichier .env à la racine du projet."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du dépôt (Job-Finder/)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Base de données ---
    db_path: str = str(DATA_DIR / "jobfinder.db")

    # --- France Travail (francetravail.io) ---
    ft_client_id: str = ""
    ft_client_secret: str = ""

    # --- Adzuna (developer.adzuna.com) ---
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # --- JSearch via RapidAPI (rapidapi.com) : couvre LinkedIn / Indeed / Glassdoor ---
    rapidapi_key: str = ""

    # --- Welcome to the Jungle (clé Algolia publique, récupérable via F12 sur le site) ---
    wttj_algolia_app_id: str = "CSEKHVMS53"
    wttj_algolia_api_key: str = ""

    # --- Email quotidien (mot de passe d'application Gmail conseillé) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    digest_email_to: str = "ced.moretti@gmail.com"

    # --- IA locale via Claude Code CLI ---
    # "auto" : utilise la CLI claude si elle est trouvée sur le poste ; "off" : désactivé.
    ai_mode: str = "auto"
    claude_cli: str = "claude"
    # Nombre max d'offres affinées par l'IA à chaque scan (les mieux classées d'abord).
    ai_max_offers_per_scan: int = 15
    # Score minimal (règles) pour qu'une offre soit soumise à l'affinage IA.
    ai_min_rule_score: int = 45

    # --- Scan quotidien ---
    scan_hour: str = "07:30"  # heure locale Europe/Paris
    timezone: str = "Europe/Paris"

    # --- Serveur ---
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
