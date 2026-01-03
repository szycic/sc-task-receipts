import os
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.notion_api import get_tasks_to_print, mark_task_as_printed, unmark_task_as_printed, mark_task_as_done, get_task_details
from app.printing import print_task_receipt

load_dotenv()

print()
print("Starting SC Task Receipts application...")
print("Base URL:", os.getenv("BASE_URL", "http://localhost:8000"))
print()

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

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
  for task in tasks:
    print_task_receipt(task["id"], task["project"], task["priority"], task["title"], task["planned_start"], task["due_date"], task["description"])
    mark_task_as_printed(task["id"])
  return {"message": f"{len(tasks)} {'tasks' if len(tasks) != 1 else 'task'} printed"}

@api_v1_router.get("/tasks/{task_id}")
def get_task(task_id: str):
  task_details = get_task_details(task_id)
  return {"message": f"Task data has been retrieved", "data": task_details}

@api_v1_router.post("/tasks/{task_id}/print")
def print_task(task_id: str):
  task = get_task_details(task_id)
  print_task_receipt(task["id"], task["project"], task["priority"], task["title"], task["planned_start"], task["due_date"], task["description"])
  mark_task_as_printed(task["id"])
  return {"message": f"Task printed"}

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