import os
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.notion_api import get_tasks_to_print, mark_task_as_printed, unmark_task_as_printed, mark_task_as_done, get_task_details
from app.printing import print_task_receipt

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

api_v1_router = APIRouter(prefix="/api/v1")

@api_v1_router.post("/tasks/print")
def print_tasks():
  tasks = get_tasks_to_print()
  for task in tasks:
    print_task_receipt(**task)
    mark_task_as_printed(task["id"])
  return {"message": f"{len(tasks)} tasks sent to printer"}

@api_v1_router.post("/tasks/{task_id}/unprint")
def unprint_task(task_id: str):
  unmark_task_as_printed(task_id)
  return {"message": f"Task unmarked as printed"}

@api_v1_router.post("/tasks/{task_id}/done")
def task_done(task_id: str):
  mark_task_as_done(task_id)
  return {"message": f"Task marked as done"}

@api_v1_router.get("/tasks/{task_id}/data")
def get_task(task_id: str):
  task_details = get_task_details(task_id)
  return {"message": f"Task data has been retrieved", "data": task_details}

app.include_router(api_v1_router)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
  tasks = get_tasks_to_print()
  return templates.TemplateResponse("index.html", {"request": request, "tasks": tasks})

@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: str):
  task = get_task_details(task_id)
  return templates.TemplateResponse("task_details.html", {"request": request, "task": task})