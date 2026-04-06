"""
Main FastAPI application entry point.
Registers all routers and configures CORS, middleware, and startup events.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.mongodb import connect_db, disconnect_db
from routes import dashboard_routes
from services.schedule_service import scheduler_loop


def _optional_route(importer, label: str):
    try:
        return importer()
    except Exception as error:
        print(f"[Startup] {label} unavailable: {error}")
        return None


agent_routes = _optional_route(lambda: __import__("routes.agent_routes", fromlist=["router"]), "Agent routes")
calendar_routes = _optional_route(lambda: __import__("routes.calendar_routes", fromlist=["router"]), "Calendar routes")
drive_routes = _optional_route(lambda: __import__("routes.drive_routes", fromlist=["router"]), "Drive routes")
email_routes = _optional_route(lambda: __import__("routes.email_routes", fromlist=["router"]), "Email routes")
github_routes = _optional_route(lambda: __import__("routes.github_routes", fromlist=["router"]), "GitHub routes")
task_routes = _optional_route(lambda: __import__("routes.task_routes", fromlist=["router"]), "Task routes")
weather_routes = _optional_route(lambda: __import__("routes.weather_routes", fromlist=["router"]), "Weather routes")
integration_routes = _optional_route(lambda: __import__("routes.integration_routes", fromlist=["router"]), "Integration routes")
schedule_routes = _optional_route(lambda: __import__("routes.schedule_routes", fromlist=["router"]), "Schedule routes")
preferences_routes = _optional_route(lambda: __import__("routes.preferences_routes", fromlist=["router"]), "Preference routes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events."""
    await connect_db()
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(scheduler_loop(stop_event))
    app.state.scheduler_stop_event = stop_event
    app.state.scheduler_task = scheduler_task
    yield
    stop_event.set()
    try:
        await scheduler_task
    except Exception as error:
        print(f"[Startup] Scheduler shutdown failed: {error}")
    await disconnect_db()


app = FastAPI(
    title="Agentic AI Digital Assistant",
    description="A production-level multi-tool AI assistant with modular feature architecture.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(dashboard_routes.router, prefix="/dashboard", tags=["Dashboard"])
if agent_routes is not None:
    app.include_router(agent_routes.router, prefix="/chat", tags=["Agent"])
if email_routes is not None:
    app.include_router(email_routes.router, prefix="/email", tags=["Email"])
if task_routes is not None:
    app.include_router(task_routes.router, prefix="/tasks", tags=["Tasks"])
if github_routes is not None:
    app.include_router(github_routes.router, prefix="/github", tags=["GitHub"])
if drive_routes is not None:
    app.include_router(drive_routes.router, prefix="/drive", tags=["Drive"])
if calendar_routes is not None:
    app.include_router(calendar_routes.router, prefix="/calendar", tags=["Calendar"])
if weather_routes is not None:
    app.include_router(weather_routes.router, prefix="/weather", tags=["Weather"])
if integration_routes is not None:
    app.include_router(integration_routes.router, prefix="/integrations", tags=["Integrations"])
if schedule_routes is not None:
    app.include_router(schedule_routes.router, prefix="/schedules", tags=["Schedules"])
if preferences_routes is not None:
    app.include_router(preferences_routes.router, prefix="/preferences", tags=["Preferences"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "Agentic AI Assistant API is running."}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
