import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = os.getenv("APP_NAME", "DocuFlow")
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
PAGES_DIR = DATA_DIR / "pages"
BRAND_DIR = DATA_DIR / "brand"
DB_PATH = DATA_DIR / "docuflow.db"
SAMPLE_DIR = BASE_DIR / "sample_data" / "invoices"
STATIC_DIR = BASE_DIR / "static"

# Groq (free tier). Without a key the app uses its built-in offline reader.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@docuflow.app")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")

# Shown on the landing page call-to-action (leave empty to send visitors to the live demo)
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "").strip()
CONTACT_WHATSAPP = os.getenv("CONTACT_WHATSAPP", "").strip()  # international format, digits only, e.g. 923001234567

# Used only for the "time saved" estimate shown in the batch summary.
MANUAL_MINUTES_PER_DOC = float(os.getenv("MANUAL_MINUTES_PER_DOC", "5"))

MAX_FILES_PER_BATCH = 100
MAX_FILE_MB = 20
MAX_PAGES_PER_DOC = 10
WORKERS = int(os.getenv("WORKERS", "2"))

for d in (UPLOAD_DIR, PAGES_DIR, BRAND_DIR):
    d.mkdir(parents=True, exist_ok=True)


def ai_enabled() -> bool:
    return bool(GROQ_API_KEY)
