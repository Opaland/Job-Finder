"""Extraction du texte et des compétences depuis un CV (PDF, DOCX ou TXT)."""
from __future__ import annotations

import io

from .textutils import contains_word, normalize

# Taxonomie de compétences QA / IT reconnues dans un CV ou une offre.
# Sert à la fois à extraire les compétences du CV et à les chercher dans les offres.
SKILL_TAXONOMY = [
    # Automatisation IHM / E2E
    "selenium", "playwright", "cypress", "protractor", "cucumber", "gherkin", "robot framework",
    # API / intégration
    "karatedsl", "karate", "rest assured", "postman", "soapui", "api rest", "soap", "graphql",
    # Performance
    "jmeter", "neoload", "gatling", "dynatrace", "locust",
    # Gestion de test / ALM
    "squash", "xray", "qtest", "alm", "quality center", "testrail", "zephyr", "squash tm",
    # Ticketing / pilotage
    "jira", "azure devops", "confluence", "redmine", "bugzilla", "power bi", "power automate",
    # CI/CD & outillage
    "jenkins", "gitlab ci", "gitlab", "github actions", "ci/cd", "docker", "git",
    # Langages / data
    "python", "sql", "java", "javascript", "typescript",
    # Méthodo & normes
    "istqb", "risk-based testing", "risk based testing", "tmmi", "tcoe", "scrum", "kanban", "agile",
    "moscow", "shift left", "session based testing", "test exploratoire", "exploratory testing",
    "iso 13485", "iec 62304", "iso 9001", "nf525", "rgpd",
    # IA & testing
    "ia", "intelligence artificielle", "llm", "rag", "agent", "agentic", "langfuse", "prompt",
    "machine learning", "nlp", "copilot", "claude", "gpt",
    # Domaines
    "sante", "e-sante", "medical", "dispositif medical", "fhir", "hl7", "dpi",
    "retail", "banque", "bancaire", "assurance", "caisse",
    # Management
    "management", "incident manager", "release management", "kpi", "sla", "support n1", "support n2",
]


def extract_text(filename: str, content: bytes) -> str:
    """Extrait le texte brut d'un CV PDF, DOCX ou TXT."""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if name.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs)
    return content.decode("utf-8", errors="replace")


def extract_skills(cv_text: str) -> list[str]:
    """Compétences de la taxonomie présentes dans le CV."""
    cv_norm = normalize(cv_text)
    found = []
    for skill in SKILL_TAXONOMY:
        if contains_word(cv_norm, skill):
            found.append(skill)
    # Dédoublonne les variantes (karate/karatedsl, gitlab/gitlab ci...)
    deduped: list[str] = []
    for s in sorted(found, key=len, reverse=True):
        if not any(s in longer for longer in deduped):
            deduped.append(s)
    return sorted(deduped)
