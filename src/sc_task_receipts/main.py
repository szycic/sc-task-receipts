import os
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sc_task_receipts.notion_api import get_tasks_to_print, mark_task_as_printed, unmark_task_as_printed, mark_task_as_done, get_task_details
from sc_task_receipts.printing import print_task_receipt

load_dotenv()

print("Starting SC Task Receipts application...")
print("Base URL:", os.getenv("BASE_URL", "http://localhost:8000"))

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = str(PACKAGE_DIR / "static")
TEMPLATES_DIR = str(PACKAGE_DIR / "templates")

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

api_v1_router = APIRouter(prefix="/api/v1")

@api_v1_router.get("/tasks")
def get_tasks():
  tasks = get_tasks_to_print()
  out = []
  for t in tasks:
    try:
      out.append(t.__dict__)
    except Exception:
      out.append(dict(t))
  return {"message": f"Tasks have been retrieved", "data": out}

@api_v1_router.post("/tasks/print")
def print_tasks():
  tasks = get_tasks_to_print()
  successes = 0
  failures = []
  for task in tasks:
    try:
      print_task_receipt(task["id"], task["project"], task["priority"], task["title"], task["planned_start"], task["due_date"], task["description"])
      mark_task_as_printed(task["id"])
      successes += 1
    except Exception as e:
      failures.append({"id": task.get("id"), "error": str(e)})

  msg = f"{successes} {'tasks' if successes != 1 else 'task'} printed"
  if failures:
    raise HTTPException(status_code=500, detail={"message": msg + f", {len(failures)} failed", "failures": failures, "successes": successes})
  return {"message": msg}

@api_v1_router.get("/tasks/{task_id}")
def get_task(task_id: str):
  task_details = get_task_details(task_id)
  return {"message": f"Task data has been retrieved", "data": task_details}

@api_v1_router.post("/tasks/{task_id}/print")
def print_task(task_id: str):
  task = get_task_details(task_id)
  try:
    print_task_receipt(task["id"], task["project"], task["priority"], task["title"], task["planned_start"], task["due_date"], task["description"])
    mark_task_as_printed(task["id"])
    return {"message": f"Task printed"}
  except Exception:
    raise HTTPException(status_code=500, detail="Failed to print")

@api_v1_router.post("/tasks/{task_id}/unprint")
def unprint_task(task_id: str):
  unmark_task_as_printed(task_id)
  return {"message": f"Task unmarked as printed"}

@api_v1_router.post("/tasks/{task_id}/done")
def task_done(task_id: str):
  mark_task_as_done(task_id)
  return {"message": f"Task marked as done"}

app.include_router(api_v1_router)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
  tasks = get_tasks_to_print()
  return templates.TemplateResponse("index.html", {"request": request, "tasks": tasks})

@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: str):
  task = get_task_details(task_id)
  return templates.TemplateResponse("task_details.html", {"request": request, "task": task})