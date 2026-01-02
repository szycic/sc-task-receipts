import os
from dotenv import load_dotenv
from notion_client import Client
from datetime import date
from datetime import datetime

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_TASKS_ID = os.getenv("NOTION_TASKS_ID")
NOTION_PROJECTS_ID = os.getenv("NOTION_PROJECTS_ID")

if not NOTION_TOKEN:
    raise RuntimeError("NOTION_TOKEN is not set in .env!")
  
if not NOTION_TASKS_ID:
    raise RuntimeError("NOTION_TASKS_ID is not set in .env!")

if not NOTION_PROJECTS_ID:
    raise RuntimeError("NOTION_PROJECTS_ID is not set in .env!")

notion = Client(auth=NOTION_TOKEN)

def get_projects_map():
    response = notion.data_sources.query(
        data_source_id=NOTION_PROJECTS_ID,
        filter={
          "property": "Archive",
          "checkbox": {
            "equals": False
          }
        }
    )
    projects = {}
    for page in response["results"]:
        projects[page["id"]] = page["properties"]["Name"]["title"][0]["plain_text"]
    return projects

def get_tasks_to_print():
  today = date.today().isoformat()
  response = notion.data_sources.query(
    data_source_id=NOTION_TASKS_ID,
    filter={
        "and": [
          {
            "property": "Done",
            "status": {
              "does_not_equal": "Done"
            }
          },
          {
            "property": "Planned for",
            "date": {
              "on_or_before": today
            }
          },
          {
            "property": "Printed",
            "checkbox": {
              "equals": False
            }
          }
        ]
      }
  )
  
  tasks = []
  projects = get_projects_map()
  
  for page in response["results"]:
    props = page["properties"]

    task = {
      "id": page["id"],
      "project": projects.get(props.get("Project")["relation"][0]["id"], "") if props.get("Project")["relation"] else "",
      "priority": props.get("Priority")["select"]["name"] if props.get("Priority")["select"] else "",
      "title": props.get("Name")["title"][0]["plain_text"] if props.get("Name")["title"] else "",
      "created_at": datetime.strftime(datetime.fromisoformat(props.get("Created at")["created_time"]), "%Y-%m-%d") if props.get("Created at")["created_time"] else "",
      "planned_for": props.get("Planned for")["date"]["start"] if props.get("Planned for")["date"] else "",
      "due_date": props.get("Due")["date"]["start"] if props.get("Due")["date"] else "",
      "description": props.get("Description")["rich_text"][0]["plain_text"] if props.get("Description")["rich_text"] else "",
    }

    tasks.append(task)

  return tasks

def mark_task_as_printed(id: str):
  notion.pages.update(
    page_id=id,
    properties={
      "Printed": {
        "checkbox": True
      }
    }
  )

def unmark_task_as_printed(id: str):
  notion.pages.update(
    page_id=id,
    properties={
      "Printed": {
        "checkbox": False
      }
    }
  )

def mark_task_as_done(id: str):
  notion.pages.update(
    page_id=id,
    properties={
      "Done": {
        "status": {
          "name": "Done"
        }
      }
    }
  )
  
def get_task_details(id: str):
  page = notion.pages.retrieve(page_id=id)
  props = page["properties"]
  projects = get_projects_map()
  
  task = {
    "id": page["id"],
    "project": projects.get(props.get("Project")["relation"][0]["id"], "") if props.get("Project")["relation"] else "",
    "priority": props.get("Priority")["select"]["name"] if props.get("Priority")["select"] else "",
    "title": props.get("Name")["title"][0]["plain_text"] if props.get("Name")["title"] else "",
    "created_at": datetime.strftime(datetime.fromisoformat(props.get("Created at")["created_time"]), "%Y-%m-%d") if props.get("Created at")["created_time"] else "",
    "planned_for": props.get("Planned for")["date"]["start"] if props.get("Planned for")["date"] else "",
    "due_date": props.get("Due")["date"]["start"] if props.get("Due")["date"] else "",
    "description": props.get("Description")["rich_text"][0]["plain_text"] if props.get("Description")["rich_text"] else "",
  }
  
  return task

if __name__ == "__main__":
  tasks = get_tasks_to_print()
  for task in tasks:
    print(task)