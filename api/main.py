"""
Task Manager - backend (API) service.

This container holds the business logic:
  - create, list, update the status of, and delete tasks
  - talk to the PostgreSQL database (via the service named "db")

Every response includes which container (replica) served the request
("served_by"). This makes load balancing, scaling and self-healing
visible during the live demo.
"""

import os
import socket
import time
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Configuration from environment variables -------------------------------
# Configuration is NOT hard-coded: stack.yml / compose.yml pass it in.
DB_HOST = os.getenv("DB_HOST", "db")          # the service NAME = its DNS name
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "tasks")
DB_USER = os.getenv("DB_USER", "tasks")
APP_VERSION = os.getenv("APP_VERSION", "dev")
HOSTNAME = socket.gethostname()               # inside Docker = the container ID


def read_db_password() -> str:
    """Read the password from a Docker secret (a file under /run/secrets).

    The secret is not passed as an environment variable, so it does not show
    up in `docker inspect` output and never ends up in the repository.
    """
    path = os.getenv("DB_PASSWORD_FILE")
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    # Fallback for running locally outside a container
    return os.getenv("DB_PASSWORD", "")


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=read_db_password(),
        connect_timeout=3,
    )


def wait_for_db_and_migrate(max_wait_s: int = 60) -> None:
    """Wait until the database is reachable, then create the table.

    IMPORTANT: Docker Swarm IGNORES `depends_on`; services start in any order.
    So the API itself has to keep retrying until PostgreSQL is available.
    If it still fails after 60 s we exit -> the Swarm restart_policy restarts us.
    """
    deadline = time.time() + max_wait_s
    while True:
        try:
            with connect() as conn:
                # Two API replicas may start at the same moment; the advisory
                # lock makes sure only one of them creates the table at a time.
                conn.execute("SELECT pg_advisory_xact_lock(42)")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id          SERIAL PRIMARY KEY,
                        title       TEXT NOT NULL,
                        status      TEXT NOT NULL DEFAULT 'todo',
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                        created_by  TEXT NOT NULL
                    )
                    """
                )
            print(f"[{HOSTNAME}] Database reachable, schema ready.", flush=True)
            return
        except psycopg.OperationalError as e:
            if time.time() > deadline:
                raise SystemExit(f"Database not reachable: {e}")
            print(f"[{HOSTNAME}] Waiting for the database... ({e.__class__.__name__})", flush=True)
            time.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db_and_migrate()
    yield


app = FastAPI(title="Task Manager API", version=APP_VERSION, lifespan=lifespan)

Status = Literal["todo", "in_progress", "done"]


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class StatusIn(BaseModel):
    status: Status


def row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "title": row[1],
        "status": row[2],
        "created_at": row[3].isoformat(),
        "created_by": row[4],
    }


# --- Endpoints ---------------------------------------------------------------

@app.get("/health")
def health():
    """Healthcheck endpoint: only reports that the process is alive and responding.

    It deliberately does NOT check the database: if the DB is briefly down,
    we don't want Swarm to restart every API container because of it.
    """
    return {"status": "ok"}


@app.get("/api/info")
def info():
    """Which replica answered, which version is running, is the database reachable."""
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except psycopg.OperationalError:
        db_ok = False
    return {"served_by": HOSTNAME, "version": APP_VERSION, "db_ok": db_ok}


@app.get("/api/tasks")
def list_tasks():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, status, created_at, created_by FROM tasks ORDER BY id DESC"
        ).fetchall()
    return {"served_by": HOSTNAME, "tasks": [row_to_dict(r) for r in rows]}


@app.post("/api/tasks", status_code=201)
def create_task(task: TaskIn):
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO tasks (title, created_by) VALUES (%s, %s) "
            "RETURNING id, title, status, created_at, created_by",
            (task.title.strip(), HOSTNAME),
        ).fetchone()
    return {"served_by": HOSTNAME, "task": row_to_dict(row)}


@app.patch("/api/tasks/{task_id}")
def update_status(task_id: int, body: StatusIn):
    with connect() as conn:
        row = conn.execute(
            "UPDATE tasks SET status = %s WHERE id = %s "
            "RETURNING id, title, status, created_at, created_by",
            (body.status, task_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"served_by": HOSTNAME, "task": row_to_dict(row)}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"served_by": HOSTNAME, "deleted": task_id}
