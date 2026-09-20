from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.routers import audit, auth, calendar, line_webhook, reports, settings as settings_router, tickets, users
from app.store import store

setup_logging()

app = FastAPI(title="Household Budget App")

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(reports.router)
app.include_router(calendar.router)
app.include_router(settings_router.router)
app.include_router(audit.router)
app.include_router(line_webhook.router)


@app.on_event("startup")
def startup() -> None:
    store.ensure_table()
    store.seed_users()
    store.seed_categories()


@app.get("/health")
def health():
    return {"ok": True}
