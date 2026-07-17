"""FastAPI Application Server for SC Task Receipts.

This module sets up routes for interacting with tasks, logbooks, and projects via
the Notion API, rendering templates, and issuing printing actions on ESC/POS networks.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Body, FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sc_task_receipts.notion_api import (
    get_tasks_to_print,
    get_todo_summary_to_print,
    get_logs_to_print,
    mark_task_as_printed,
    unmark_task_as_printed,
    mark_task_as_done,
    get_task_details,
    refresh_projects,
)
from sc_task_receipts.printing import (
    print_task_receipt,
    print_todo_summary_receipt,
    print_logbook_receipt,
)

# Load environment configuration
load_dotenv()

print("Starting SC Task Receipts application...")
print("Base URL:", os.getenv("BASE_URL", "http://localhost:8000"))

# Setup static files and templates directories
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = str(PACKAGE_DIR / "static")
TEMPLATES_DIR = str(PACKAGE_DIR / "templates")

# Initialize FastAPI app
app = FastAPI(
    title="SC Task Receipts API",
    description="Backend API and dashboard service for printing Notion tasks to a physical thermal printer.",
)

# Mount static asset files (CSS, Icons, etc.)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Mount HTML rendering templates using Jinja2
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# API v1 Router definition
api_v1_router = APIRouter(prefix="/api/v1")


@api_v1_router.get("/tasks")
def get_tasks() -> dict:
    """Retrieve all pending tasks to print from Notion.

    Returns:
        A dictionary containing a message and the task list data.
    """
    tasks = get_tasks_to_print()
    out = []
    for t in tasks:
        try:
            out.append(t.__dict__)
        except Exception:
            out.append(dict(t))
    return {"message": "Tasks have been retrieved", "data": out}


@api_v1_router.post("/tasks/print")
def print_tasks() -> dict:
    """Trigger printing of all queued/unprinted tasks.

    Iterates over all unprinted tasks, prints them sequentially, and marks
    them as printed in Notion. Raises 500 status on partial or full failure.

    Returns:
        A dictionary detailing success status.
    """
    tasks = get_tasks_to_print()
    successes = 0
    failures = []
    for task in tasks:
        try:
            print_task_receipt(
                task["id"],
                task["project"],
                task["priority"],
                task["title"],
                task["planned_start"],
                task["due_date"],
                task["description"],
            )
            mark_task_as_printed(task["id"])
            successes += 1
        except Exception as e:
            failures.append({"id": task.get("id"), "error": str(e)})

    msg = f"{successes} {'tasks' if successes != 1 else 'task'} printed"
    if failures:
        raise HTTPException(
            status_code=500,
            detail={
                "message": msg + f", {len(failures)} failed",
                "failures": failures,
                "successes": successes,
            },
        )
    return {"message": msg}


@api_v1_router.post("/tasks/summary/print")
def print_todo_summary() -> dict:
    """Format and print a ToDo daily summary receipt.

    Retrieves tasks planned for today or tasks without start dates, and prints
    them in a list format on the thermal printer.

    Returns:
        A status message indicating print completion.
    """
    tasks = get_todo_summary_to_print()
    if not tasks:
        return {"message": "No tasks found for summary"}
    try:
        print_todo_summary_receipt(tasks)
        return {"message": "ToDo summary printed"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"message": "ToDo summary failed to print", "error": str(e)},
        )


@api_v1_router.post("/tasks/logbook/print")
def print_logbook(target_date: str = Body(..., embed=True)) -> dict:
    """Print the Notion logbook list for a specified target date.

    Args:
        target_date: The ISO date string (YYYY-MM-DD) for which logs are printed.

    Returns:
        A status message indicating print status.
    """
    logs = get_logs_to_print(target_date)
    if not logs:
        return {"message": f"No logs found for {target_date}"}
    try:
        print_logbook_receipt(target_date, logs)
        return {"message": "Logbook printed"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"message": "Logbook failed to print", "error": str(e)},
        )


@api_v1_router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    """Fetch structured details of a single task.

    Args:
        task_id: The Notion page ID of the task.

    Returns:
        A dictionary containing the task fields.
    """
    task_details = get_task_details(task_id)
    return {"message": "Task data has been retrieved", "data": task_details}


@api_v1_router.post("/tasks/{task_id}/print")
def print_task(task_id: str) -> dict:
    """Print a single task receipt by ID.

    Prints the receipt, and immediately marks the task as printed in Notion.

    Args:
        task_id: The Notion page ID of the task.

    Returns:
        A status message.
    """
    task = get_task_details(task_id)
    try:
        print_task_receipt(
            task["id"],
            task["project"],
            task["priority"],
            task["title"],
            task["planned_start"],
            task["due_date"],
            task["description"],
        )
        mark_task_as_printed(task["id"])
        return {"message": "Task printed"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to print")


@api_v1_router.post("/tasks/{task_id}/unprint")
def unprint_task(task_id: str) -> dict:
    """Reset the 'Printed' status checkmark of a task to false in Notion.

    Args:
        task_id: The Notion page ID of the task.

    Returns:
        A confirmation message.
    """
    unmark_task_as_printed(task_id)
    return {"message": "Task unmarked as printed"}


@api_v1_router.post("/tasks/{task_id}/done")
def task_done(task_id: str) -> dict:
    """Mark a task's status as 'Done' in Notion.

    Args:
        task_id: The Notion page ID of the task.

    Returns:
        A confirmation message.
    """
    mark_task_as_done(task_id)
    return {"message": "Task marked as done"}


@api_v1_router.post("/projects/refresh")
def api_refresh_projects() -> dict:
    """Invalidate the local projects name cache, triggering a fresh fetch on the next call.

    Returns:
        A confirmation message.
    """
    refresh_projects()
    return {"message": "Projects refreshed"}


# Register all API endpoints under app routing
app.include_router(api_v1_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render the Main Task Dashboard UI.

    Retrieves tasks to print and returns the index dashboard HTML page.
    """
    tasks = get_tasks_to_print()
    return templates.TemplateResponse(
        "index.html", {"request": request, "tasks": tasks}
    )


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: str) -> HTMLResponse:
    """Render the Task Details page dashboard.

    Args:
        request: The FastAPI request context.
        task_id: The Notion page ID of the task.
    """
    task = get_task_details(task_id)
    return templates.TemplateResponse(
        "task_details.html", {"request": request, "task": task}
    )