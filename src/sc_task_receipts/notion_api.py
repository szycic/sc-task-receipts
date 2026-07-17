"""Notion API Integration Module for SC Task Receipts.

Fetches projects, tasks, and logbook entries from Notion, manages local projects caching,
and updates status fields (such as 'Printed' and 'Status').
"""

import os
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from notion_client import Client

# Load environment configuration
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_TASKS_ID = os.getenv("NOTION_TASKS_ID")
NOTION_PROJECTS_ID = os.getenv("NOTION_PROJECTS_ID")
NOTION_LOGBOOK_ID = os.getenv("NOTION_LOGBOOK_ID")

# Ensure required environment configurations are loaded
if not NOTION_TOKEN:
    raise RuntimeError("NOTION_TOKEN is not set in .env!")
  
if not NOTION_TASKS_ID:
    raise RuntimeError("NOTION_TASKS_ID is not set in .env!")

if not NOTION_PROJECTS_ID:
    raise RuntimeError("NOTION_PROJECTS_ID is not set in .env!")
  
if not NOTION_LOGBOOK_ID:
    raise RuntimeError("NOTION_LOGBOOK_ID is not set in .env!")

# Initialize Notion API client
notion = Client(auth=NOTION_TOKEN)

# In-memory dictionary cache mapping project ID -> project Name string
_projects_cache = None


def _invalidate_projects_cache() -> None:
    """Invalidate the local in-memory cache of project IDs and names."""
    global _projects_cache
    _projects_cache = None


def refresh_projects() -> None:
    """Force-refreshes the projects cache from Notion.

    Invalidates the current cache, causing the next query to re-fetch
    projects directly from the Notion database.
    """
    _invalidate_projects_cache()


def get_projects_map() -> dict:
    """Retrieve the map of project IDs to project names.

    Queries Notion to build the map if the cache is empty (cold start),
    otherwise returns the cached dictionary directly.

    Returns:
        A dictionary mapping Notion project UUID strings to their plain-text names.
    """
    global _projects_cache
    if _projects_cache is not None:
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
    return projects


def _ensure_projects_for_ids(project_ids: set) -> dict:
    """Ensure that the local projects cache contains all requested project IDs.

    If any of the IDs are not found in the cache, the cache is invalidated
    and a fresh list of active projects is fetched from Notion.

    Args:
        project_ids: A set of project UUID strings to check.

    Returns:
        The updated projects mapping dictionary.
    """
    if not project_ids:
        return get_projects_map()
    projects = get_projects_map()
    missing = [pid for pid in project_ids if pid not in projects]
    if missing:
        _invalidate_projects_cache()
        projects = get_projects_map()
    return projects


def _parse_date_for_sort(s: str):
    """Parse an ISO date/datetime string into a date object for sorting.

    Args:
        s: The ISO formatted string to parse, or "NONE".

    Returns:
        A datetime.date object if parsing succeeds, otherwise None.
    """
    if not s or s == "NONE":
        return None
    try:
        # Handles both YYYY-MM-DD and YYYY-MM-DDTHH:MM:SS format variations
        if 'T' in s:
            return datetime.fromisoformat(s).date()
        return date.fromisoformat(s)
    except Exception:
        return None
      

def _sort_key(t: dict) -> tuple:
    """Calculate the sorting key tuple for a task dictionary.

    Sort order rules:
    1. due_date (earliest first, missing last)
    2. priority (High -> Medium -> Low -> Optional -> Unknown)
    3. planned_start (earliest first, missing last)
    4. title (alphabetical order)

    Args:
        t: The task dictionary.

    Returns:
        A tuple of comparable values used by list sorting algorithms.
    """
    due = _parse_date_for_sort(t.get("due_date"))
    planned = _parse_date_for_sort(t.get("planned_start"))

    # Map priority string values to sorting ranks
    priority_str = (t.get("priority") or "").strip().lower()
    priority_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
        "optional": 3,
    }
    pr_rank = priority_order.get(priority_str, 4)

    # Returns (due_missing, due_val, priority_rank, planned_missing, planned_val, title)
    return (
        due is None,
        due or date.max,
        pr_rank,
        planned is None,
        planned or date.max,
        (t.get("title") or "").lower(),
    )
  

def _fetch_tasks_with_filter(filter_dict: dict) -> list:
    """Fetch and parse tasks from Notion using a specific filter query.

    Also identifies related projects and resolves their names against the project cache.

    Args:
        filter_dict: The filter configuration dictionary sent to Notion API.

    Returns:
        A sorted list of task dictionaries.
    """
    response = notion.data_sources.query(
        data_source_id=NOTION_TASKS_ID,
        filter=filter_dict
    )
  
    # Extract referenced project IDs to verify they exist in cache
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


def _fetch_logs_with_filter_sort(filter_dict: dict, sorts: list) -> list:
    """Fetch and parse logbook entries from Notion using filter and sort parameters.

    Args:
        filter_dict: Notion query filter structure.
        sorts: Notion query sorting constraints.

    Returns:
        A list of parsed log dictionaries.
    """
    response = notion.data_sources.query(
        data_source_id=NOTION_LOGBOOK_ID,
        filter=filter_dict,
        sorts=sorts
    )
  
    # Gather project relations to optimize resolution
    referenced_ids = set()
    for page in response.get("results", []):
        props = page.get("properties", {})
        rel = props.get("Project") and props.get("Project").get("relation")
        if rel:
            for r in rel:
                if isinstance(r, dict) and r.get("id"):
                    referenced_ids.add(r.get("id"))
          
    projects = _ensure_projects_for_ids(referenced_ids)
    logs = []
  
    for page in response.get("results", []):
        props = page.get("properties", {})

        log = {
            "id": page.get("id"),
            "title": props.get("Name")["title"][0]["plain_text"] if props.get("Name") and props.get("Name").get("title") else "",
            "logged_on": props.get("Logged on")["date"]["start"] if props.get("Logged on") and props.get("Logged on").get("date") else "",
            "project": projects.get(props.get("Project")["relation"][0]["id"], "") if props.get("Project") and props.get("Project").get("relation") else "",
            "status": props.get("Status")["select"]["name"] if props.get("Status") and props.get("Status").get("select") else "",
            "log": props.get("Log")["rich_text"][0]["plain_text"] if props.get("Log") and props.get("Log").get("rich_text") else "",
        }

        logs.append(log)
    
    return logs


def get_tasks_to_print() -> list:
    """Query tasks queued for printing (uncompleted, started, not yet printed).

    Returns:
        A sorted list of task dictionaries matching the criteria.
    """
    today = date.today().isoformat()
    filter_dict = {
        "or": [
            {
                "and": [
                    {
                        "property": "Status",
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
                        "property": "Status",
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


def get_todo_summary_to_print() -> list:
    """Query tasks to compile the daily ToDo summary (uncompleted, planned for today or undated).

    Returns:
        A sorted list of tasks.
    """
    today = date.today().isoformat()
    filter_dict = {
        "or": [
            {
                "and": [
                    {
                        "property": "Status",
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
                        "property": "Status",
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


def get_logs_to_print(target_date: str) -> list:
    """Fetch all logbook records created on a target date.

    Args:
        target_date: The date string (YYYY-MM-DD) to retrieve logs for.

    Returns:
        A list of logs sorted ascending by logged timestamp.
    """
    day_date = date.fromisoformat(target_date)
    next_day_date = day_date + timedelta(days=1)
  
    filter_dict = {
        "and": [
            {
                "property": "Logged on",
                "date": {
                    "on_or_after": day_date.isoformat()
                }
            },
            {
                "property": "Logged on",
                "date": {
                    "before": next_day_date.isoformat()
                }
            }
        ]
    }
  
    sorts = [
        {
            "property": "Logged on",
            "direction": "ascending"
        }
    ]
  
    return _fetch_logs_with_filter_sort(filter_dict, sorts)


def mark_task_as_printed(id: str) -> None:
    """Set the 'Printed' checkmark property to True for a specific Notion page.

    Args:
        id: Notion Page ID of the task.
    """
    notion.pages.update(
        page_id=id,
        properties={
            "Printed": {
                "checkbox": True
            }
        }
    )


def unmark_task_as_printed(id: str) -> None:
    """Set the 'Printed' checkmark property to False for a specific Notion page.

    Args:
        id: Notion Page ID of the task.
    """
    notion.pages.update(
        page_id=id,
        properties={
            "Printed": {
                "checkbox": False
            }
        }
    )


def mark_task_as_done(id: str) -> None:
    """Update status of a task to 'Done' in Notion.

    Args:
        id: Notion Page ID of the task.
    """
    notion.pages.update(
        page_id=id,
        properties={
            "Status": {
                "status": {
                    "name": "Done"
                }
            }
        }
    )
  

def get_task_details(id: str) -> dict:
    """Fetch detail fields of a single task page by ID.

    Args:
        id: Notion Page ID of the task.

    Returns:
        A dictionary containing parsed task properties.
    """
    page = notion.pages.retrieve(page_id=id)
    props = page.get("properties", {})
  
    # Ensure projects cache contains referenced project ID
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
        "done": True if props.get("Status") and props.get("Status").get("status") and props.get("Status")["status"].get("name") == "Done" else False,
    }
  
    return task


if __name__ == "__main__":
    tasks = get_tasks_to_print()
    for task in tasks:
        print(task)