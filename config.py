import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    MONGO_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "twitter_link_store")
    ADMIN_BOT_TOKEN: str = os.getenv("ADMIN_BOT_TOKEN", "")
    BASE_URL: str = os.getenv("WEBHOOK_BASE_URL", "")
    ADMIN_TELEGRAM_USER_ID: int = int(os.getenv("ADMIN_TELEGRAM_USER_ID", "0"))
    INGRESS_SECRET: str = os.getenv("INGRESS_SECRET", "")

settings = Settings()

if not settings.ADMIN_BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN missing in .env")
if not settings.BASE_URL:
    print("[config] ⚠️ Warning: WEBHOOK_BASE_URL missing — child webhooks won’t be set.")