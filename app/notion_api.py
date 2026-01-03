import os
from dotenv import load_dotenv
from notion_client import Client
from datetime import date

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

# Simple projects cache (no TTL): keep projects in memory until we see an unknown project id
_projects_cache = None

def _invalidate_projects_cache():
    global _projects_cache
    _projects_cache = None
    # small debug trace when cache is invalidated
    print("projects: invalidated", flush=True)

def get_projects_map():
    """Return a map of project_id -> project_name. Cached in _projects_cache until invalidated.
    The cache is refreshed only when _invalidate_projects_cache() is called (by _ensure_projects_for_ids).
    """
    global _projects_cache
    if _projects_cache is not None:
        # debug: indicate a cache hit
        print("projects: cached", flush=True)
        return _projects_cache

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
    for page in response.get("results", []):
        # defensive access
        name_prop = page.get("properties", {}).get("Name", {}).get("title")
        name = name_prop[0].get("plain_text") if isinstance(name_prop, list) and len(name_prop) > 0 else ""
        projects[page.get("id")] = name

    _projects_cache = projects
    # debug: indicate the cache was refreshed from Notion
    print("projects: refreshed", flush=True)
    return projects


def _ensure_projects_for_ids(project_ids):
    """Ensure cached projects contain all project_ids. If some are missing, invalidate and re-fetch cache.
    Returns the (possibly refreshed) projects map.
    """
    if not project_ids:
        return get_projects_map()
    projects = get_projects_map()
    missing = [pid for pid in project_ids if pid not in projects]
    if missing:
        # Invalidate and re-fetch once when we see an unknown project id
        _invalidate_projects_cache()
        projects = get_projects_map()
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
            "property": "Planned start",
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
  
  # collect referenced project ids from the result set so we can refresh cache only when needed
  referenced_ids = set()
  for page in response.get("results", []):
    props = page.get("properties", {})
    rel = props.get("Project") and props.get("Project").get("relation")
    if rel:
      for r in rel:
        if isinstance(r, dict) and r.get("id"):
          referenced_ids.add(r.get("id"))
          
  projects = _ensure_projects_for_ids(referenced_ids)
  tasks = []
  
  for page in response.get("results", []):
    props = page.get("properties", {})

    task = {
      "id": page.get("id"),
      "project": projects.get(props.get("Project")["relation"][0]["id"], "") if props.get("Project") and props.get("Project").get("relation") else "",
      "priority": props.get("Priority")["select"]["name"] if props.get("Priority") and props.get("Priority").get("select") else "",
      "title": props.get("Name")["title"][0]["plain_text"] if props.get("Name") and props.get("Name").get("title") else "",
      "planned_start": props.get("Planned start")["date"]["start"] if props.get("Planned start") and props.get("Planned start").get("date") else "NONE",
      "due_date": props.get("Due date")["date"]["start"] if props.get("Due date") and props.get("Due date").get("date") else "NONE",
      "description": props.get("Description")["rich_text"][0]["plain_text"] if props.get("Description") and props.get("Description").get("rich_text") else "",
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
  props = page.get("properties", {})
  
  # ensure projects cache contains referenced project id (if any)
  rel = props.get("Project") and props.get("Project").get("relation")
  referenced_id = None
  if rel and isinstance(rel, list) and len(rel) > 0 and isinstance(rel[0], dict):
    referenced_id = rel[0].get("id")
    
  projects = _ensure_projects_for_ids({referenced_id} if referenced_id else set())

  task = {
    "id": page.get("id"),
    "project": projects.get(props.get("Project")["relation"][0]["id"], "") if props.get("Project") and props.get("Project").get("relation") else "",
    "priority": props.get("Priority")["select"]["name"] if props.get("Priority") and props.get("Priority").get("select") else "",
    "title": props.get("Name")["title"][0]["plain_text"] if props.get("Name") and props.get("Name").get("title") else "",
    "planned_start": props.get("Planned start")["date"]["start"] if props.get("Planned start") and props.get("Planned start").get("date") else "NONE",
    "due_date": props.get("Due date")["date"]["start"] if props.get("Due date") and props.get("Due date").get("date") else "NONE",
    "description": props.get("Description")["rich_text"][0]["plain_text"] if props.get("Description") and props.get("Description").get("rich_text") else "",
    "printed": props.get("Printed")["checkbox"] if props.get("Printed") and props.get("Printed").get("checkbox") else False,
    "done": True if props.get("Done") and props.get("Done").get("status") and props.get("Done")["status"].get("name") == "Done" else False,
  }
  
  return task

if __name__ == "__main__":
  tasks = get_tasks_to_print()
  for task in tasks:
    print(task)