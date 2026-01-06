import os
import textwrap
from dotenv import load_dotenv
from escpos.printer import Network
from datetime import datetime
from sc_task_receipts.db import peek_next_receipt_number, commit_receipt_number, RECEIPT_NUMBER_RESET_AT

load_dotenv()

PRINTER_IP = os.getenv("PRINTER_IP")
PRINTER_PORT = int(os.getenv("PRINTER_PORT", 9100))
PAPER_WIDTH_MM = int(os.getenv("PAPER_WIDTH_MM", 80))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SPECIAL_INDENT = int(os.getenv("SPECIAL_INDENT", 4))
NO_PROJECT_TEXT = os.getenv("NO_PROJECT_TEXT", "No Project")
  
PIXELS_MAP = {58: 384, 80: 576}
MEDIA_WIDTH_PIXELS = PIXELS_MAP.get(PAPER_WIDTH_MM, 576)

CHARS_PER_LINE_MAP = {58: 32, 80: 48}
CHARS_PER_LINE = CHARS_PER_LINE_MAP.get(PAPER_WIDTH_MM, 48)

if not PRINTER_IP:
    raise ValueError("PRINTER_IP is not set in .env!")


def print_task_receipt(id: str, project: str, priority: str, title: str, planned_start: str, due_date: str, description: str):
  """Print a task receipt.

  Args:
      id (str): The ID of the task.
      project (str): The project of the task.
      priority (str): The priority of the task.
      title (str): The title of the task.
      planned_start (str): The planned start date for the task.
      due_date (str): The due date of the task.
      description (str): The description of the task.
  """
  try:
    printer = Network(PRINTER_IP, PRINTER_PORT, timeout=10)
    printer.profile.profile_data["media"]["width"]["pixels"] = MEDIA_WIDTH_PIXELS
    
    number = peek_next_receipt_number()

    # MAIN HEADER: Project
    printer._raw(b'\x1b\x40')  # ESC/POS command to initialize printer
    printer._raw(b'\x1b\x45\x01')  # ESC/POS command for bold on
    printer._raw(b'\x1b\x4d\x01') # ESC/POS command for emphasized mode on
    printer._raw(b'\x1d\x21\x22')  # ESC/POS command for change width and height
    printer.set(align='right')
    printer.text(f"{str(number).zfill(len(str(RECEIPT_NUMBER_RESET_AT)))}\n")
    printer._raw(b'\x1d\x21\x11')  # ESC/POS command for change width and height
    printer.set(align='center')
    if project and project.strip():
      printer.text(f"{project}\n")
    else:
      printer.text(f"{NO_PROJECT_TEXT}\n")

    # SECONDARY HEADER: Priority
    if priority and priority.strip():
      printer.text(f"{priority}\n\n")
    else:
      printer.text("\n")
    printer._raw(b'\x1d\x21\x00') # ESC/POS command for normal size
    printer._raw(b'\x1b\x45\x00')  # ESC/POS command for bold off
    printer._raw(b'\x1b\x4d\x00') # ESC/POS command for emphasized mode off
    printer.text("-" * CHARS_PER_LINE + "\n\n")

    # TASK
    printer.set(align='left')
    printer.text(f"Task\n")
    wrapped_title = textwrap.wrap(title, width=CHARS_PER_LINE - SPECIAL_INDENT)
    for line in wrapped_title:
      printer.text(f"{' ' * SPECIAL_INDENT}{line}\n")
    printer.text("\n")
        
    # DATES
    labels_and_dates = [
        ("Planned start", planned_start if planned_start and planned_start.strip() else "—"),
        ("Due date", due_date if due_date and due_date.strip() else "—"),
    ]
    for label, value in labels_and_dates:
      printer.text(f"{label}{value.rjust(CHARS_PER_LINE - len(label))}\n")
    printer.text("\n")

    # DESCRIPTION (only if not empty)
    if description and description.strip():
      printer.text("Description\n")
      wrapped_description = textwrap.wrap(description, width=CHARS_PER_LINE - SPECIAL_INDENT)
      for line in wrapped_description:
        printer.text(f"{' ' * SPECIAL_INDENT}{line}\n")
      printer.text("\n")
    printer.set(align='center')
    printer.text("-" * CHARS_PER_LINE + "\n")
      
    # QR
    qr_data = f"{BASE_URL}/tasks/{id}"
    printer.set(align='center')
    printer.qr(qr_data, size=6)
    printer.text("Scan to mark as DONE\n\n")
    printer.text("-" * CHARS_PER_LINE + "\n\n")

    # FOOTER: print timestamp
    printer.set(align='center')
    printer.text(f"Printed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # CUT
    printer.cut()
    printer.close()
    commit_receipt_number(number)
    print("✅ Task printed successfully!")
    return True

  except Exception as e:
    print("❌ Failed to print:", e)
    raise

def print_todo_summary_receipt(list_of_tasks):
  """Print a todo summary receipt."""
  try:
    printer = Network(PRINTER_IP, PRINTER_PORT, timeout=10)
    printer.profile.profile_data["media"]["width"]["pixels"] = MEDIA_WIDTH_PIXELS

    # MAIN HEADER
    printer._raw(b'\x1b\x40')  # ESC/POS command to initialize printer
    printer.set(align='center')
    printer.text("ToDo Summary\n")
    printer.text(f"{len(list_of_tasks)} tasks\n")
    printer.text("-" * CHARS_PER_LINE + "\n")

    for task in list_of_tasks:
      printer.set(align='left')
      wrapped_title = textwrap.wrap(task['title'], width=CHARS_PER_LINE - 2)
      for line in wrapped_title:
        if line == wrapped_title[0]:
          printer.text(f"• {line}\n")
        else:
          printer.text(f"{line}\n")
      if task['due_date'] and task['due_date'].strip():
        printer.text(f"  Due: {task['due_date']}\n")
      if task['priority'] and task['priority'].strip():
        printer.text(f"  Prio: {task['priority']}\n")
      if task['planned_start'] and task['planned_start'].strip():
        printer.text(f"  Start: {task['planned_start']}\n")
      if task['project'] and task['project'].strip():
        printer.text(f"  Project: {task['project']}\n")
      if task != list_of_tasks[-1]:
        printer.text("\n")

    # FOOTER: print timestamp
    printer.set(align='center')
    printer.text("-" * CHARS_PER_LINE + "\n")
    printer.text(f"Printed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # CUT
    printer.cut()
    printer.close()
    print("✅ ToDo summary printed successfully!")
    return True

  except Exception as e:
    print("❌ Failed to print:", e)
    raise

if __name__ == "__main__":
  #print_task_receipt("12345", "", "", "Task Name Here", "", "", "This is an example task description that is a little long and needs to be wrapped properly.")
  print_todo_summary_receipt([
    {
      "id": "task1",
      "project": "Project Alpha",
      "priority": "High",
      "title": "[AP] Special financial knowleedge workshop so fun to attend",
      "planned_start": "2024-07-01",
      "due_date": "2024-07-05",
      "description": "Finish the quarterly financial report and send it to the management team."
    },
    {
      "id": "task2",
      "project": "",
      "priority": "Low",
      "title": "Organize workspace",
      "planned_start": "",
      "due_date": "",
      "description": "Clean and organize the physical and digital workspace for better productivity."
    }
  ])