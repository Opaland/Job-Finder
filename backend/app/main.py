"""Job Finder — application locale de recherche d'emploi QA pour Cédric Moretti.

Backend FastAPI : agrège les offres de plusieurs sites d'emploi, les classe par
rapport au CV, produit un point quotidien et sert le frontend React buildé.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST
from .database import SessionLocal, engine, ensure_schema
from .routers import digests, offers, profile, scans, sources, stats
from .services.scheduler import start_scheduler, stop_scheduler
from .services.seeding import ensure_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema(engine)
    db = SessionLocal()
    try:
        ensure_profile(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Job Finder", lifespan=lifespan)

# Application 100 % locale : CORS ouvert pour simplifier le développement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(offers.router)
app.include_router(profile.router)
app.include_router(scans.router)
app.include_router(digests.router)
app.include_router(sources.router)
app.include_router(stats.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Sert le frontend React buildé (frontend/dist) si présent.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = FRONTEND_DIST / path
        if path and file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
