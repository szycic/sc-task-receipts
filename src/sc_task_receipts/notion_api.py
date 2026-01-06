import os
from dotenv import load_dotenv
from notion_client import Client
from datetime import date, datetime

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

_projects_cache = None

def _invalidate_projects_cache():
    """Helper to invalidate the in-memory projects cache."""
    global _projects_cache
    _projects_cache = None
    #print("projects: cache invalidated")


def refresh_projects():
    """Force-refresh the projects cache from Notion and return how many projects were loaded.
    This invalidates the cache and then calls get_projects_map() which will re-populate it.
    """
    _invalidate_projects_cache()
    #print("projects: cache refreshed")

def get_projects_map():
    """Return a map of project_id -> project_name. Cached in _projects_cache until invalidated.
    The cache is refreshed only when `invalidate_projects_cache()` is called.
    """
    global _projects_cache
    if _projects_cache is not None:
        #print("projects: cache hit")
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
        name_prop = page.get("properties", {}).get("Name", {}).get("title")
        name = name_prop[0].get("plain_text") if isinstance(name_prop, list) and len(name_prop) > 0 else ""
        projects[page.get("id")] = name

    _projects_cache = projects
    #print("projects: cache refreshed")
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

def _parse_date_for_sort(s):
    """Return a date object for ISO date string s, or None if missing/invalid."""
    if not s or s == "NONE":
        return None
    try:
        # handle both date-only and datetime ISO strings
        if 'T' in s:
            return datetime.fromisoformat(s).date()
        return date.fromisoformat(s)
    except Exception:
        return None
      
def _sort_key(t):
    """Sort by: 1) due_date (earliest first, missing last), 2) priority (High->Medium->Low->Optional), 3) planned_start (earliest first, missing last), 4) title."""
    due = _parse_date_for_sort(t.get("due_date"))
    planned = _parse_date_for_sort(t.get("planned_start"))

    # Priority ordering: lower number sorts first (higher priority)
    priority_str = (t.get("priority") or "").strip().lower()
    priority_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
        "optional": 3,
    }
    pr_rank = priority_order.get(priority_str, 4)

    # (due_missing, due_value, priority_rank, planned_missing, planned_value, title)
    return (
        due is None,
        due or date.max,
        pr_rank,
        planned is None,
        planned or date.max,
        (t.get("title") or "").lower(),
    )
  
def _fetch_tasks_with_filter(filter_dict):
  """Fetch tasks from Notion with the given filter."""
  response = notion.data_sources.query(
    data_source_id=NOTION_TASKS_ID,
    filter=filter_dict
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
      "planned_start": props.get("Planned start")["date"]["start"] if props.get("Planned start") and props.get("Planned start").get("date") else "",
      "due_date": props.get("Due date")["date"]["start"] if props.get("Due date") and props.get("Due date").get("date") else "",
      "description": props.get("Description")["rich_text"][0]["plain_text"] if props.get("Description") and props.get("Description").get("rich_text") else "",
    }

    tasks.append(task)

  tasks.sort(key=_sort_key)
  return tasks

def get_tasks_to_print():
  """Return list of tasks to print (not done, planned start <= today or no planned start, not printed)."""
  today = date.today().isoformat()
  filter_dict={
      "or": [
        {
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
        },
        {
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
                "is_empty": True
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
      ]
    }
  
  return _fetch_tasks_with_filter(filter_dict)

def get_todo_summary_to_print():
  """Return list of tasks for daily summary (not done, planned start <= today or no planned start)."""
  today = date.today().isoformat()
  filter_dict={
      "or": [
        {
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
            }
          ]
        },
        {
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
                "is_empty": True
              }
            }
          ]
        }
      ]
    }
  
  return _fetch_tasks_with_filter(filter_dict)

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
    "planned_start": props.get("Planned start")["date"]["start"] if props.get("Planned start") and props.get("Planned start").get("date") else "",
    "due_date": props.get("Due date")["date"]["start"] if props.get("Due date") and props.get("Due date").get("date") else "",
    "description": props.get("Description")["rich_text"][0]["plain_text"] if props.get("Description") and props.get("Description").get("rich_text") else "",
    "printed": props.get("Printed")["checkbox"] if props.get("Printed") and props.get("Printed").get("checkbox") else False,
    "done": True if props.get("Done") and props.get("Done").get("status") and props.get("Done")["status"].get("name") == "Done" else False,
  }
  
  return task

if __name__ == "__main__":
  tasks = get_tasks_to_print()
  for task in tasks:
    print(task)