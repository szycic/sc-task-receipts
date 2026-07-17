"""ESC/POS Printing Module for SC Task Receipts.

Connects to a thermal printer over TCP/IP (Network) and outputs task details,
daily summaries, and logbook entries formatted specifically for receipt paper sizes.
"""

import os
import textwrap
from datetime import datetime
from dotenv import load_dotenv
from escpos.printer import Network
from sc_task_receipts.db import peek_next_receipt_number, commit_receipt_number, RECEIPT_NUMBER_RESET_AT

# Load configuration values from environment variables
load_dotenv()

# TCP/IP settings for the receipt printer
PRINTER_IP = os.getenv("PRINTER_IP")
PRINTER_PORT = int(os.getenv("PRINTER_PORT", 9100))

# Width config (usually 58 or 80 mm)
PAPER_WIDTH_MM = int(os.getenv("PAPER_WIDTH_MM", 80))

# Base URL to embed in QR codes
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Character indentation spaces for body paragraph blocks (e.g. descriptions, logs)
SPECIAL_INDENT = int(os.getenv("SPECIAL_INDENT", 4))

# Text placeholder when project is not set in Notion
NO_PROJECT_TEXT = os.getenv("NO_PROJECT_TEXT", "No Project")
  
# Map paper width in mm to pixel values used by printer graphics
PIXELS_MAP = {58: 384, 80: 576}
MEDIA_WIDTH_PIXELS = PIXELS_MAP.get(PAPER_WIDTH_MM, 576)

# Map paper width in mm to average characters-per-line capacity for standard font size
CHARS_PER_LINE_MAP = {58: 32, 80: 48}
CHARS_PER_LINE = CHARS_PER_LINE_MAP.get(PAPER_WIDTH_MM, 48)

# Note writing space configurations
PRINT_NOTES = os.getenv("PRINT_NOTES", "1") == "1"
PRINT_NOTES_LINES = int(os.getenv("PRINT_NOTES_LINES", 6))

# Verify that target printer destination is loaded
if not PRINTER_IP:
    raise ValueError("PRINTER_IP is not set in .env!")


def print_task_receipt(
    id: str,
    project: str,
    priority: str,
    title: str,
    planned_start: str,
    due_date: str,
    description: str,
) -> bool:
    """Connect to the network printer and print a dedicated task receipt.

    Uses raw ESC/POS formatting commands to adjust font weight/size, prints
    metadata, wraps descriptions, appends note spaces, adds a scan-to-done QR code,
    cuts the paper, and registers the printed counter ID locally.

    Args:
        id: Notion Page ID of the task (used in QR code link).
        project: Project name.
        priority: Priority tag (e.g. High, Medium, Low).
        title: Title of the task.
        planned_start: Planned start date string.
        due_date: Due date string.
        description: Description of the task.

    Returns:
        True if printing succeeds.
    """
    try:
        # Establish connection with thermal printer
        printer = Network(PRINTER_IP, PRINTER_PORT, timeout=10)
        printer.profile.profile_data["media"]["width"]["pixels"] = MEDIA_WIDTH_PIXELS
        
        # Get next receipt sequence number (e.g. #01)
        number = peek_next_receipt_number()

        # Initialize printer state
        printer._raw(b"\x1b\x40")       # ESC/POS command to initialize printer
        printer._raw(b"\x1b\x45\x01")   # ESC/POS command for bold text on
        printer._raw(b"\x1b\x4d\x01")   # ESC/POS command for emphasized mode on
        printer._raw(b"\x1d\x21\x22")   # ESC/POS command for change width and height (large sequence number)
        printer.set(align="right")
        printer.text(f"{str(number).zfill(len(str(RECEIPT_NUMBER_RESET_AT)))}\n")
        
        # Format and center main header
        printer._raw(b"\x1d\x21\x11")   # Reset size to double height/width
        printer.set(align="center")
        if project and project.strip():
            printer.text(f"{project}\n")
        else:
            printer.text(f"{NO_PROJECT_TEXT}\n")

        # Priority header block
        if priority and priority.strip():
            printer.text(f"{priority}\n\n")
        else:
            printer.text("\n")
            
        printer._raw(b"\x1d\x21\x00")   # Reset to normal characters
        printer._raw(b"\x1b\x45\x00")   # Bold off
        printer._raw(b"\x1b\x4d\x00")   # Emphasized mode off
        printer.text("-" * CHARS_PER_LINE + "\n\n")

        # Task title (wrap text dynamically based on column length)
        printer.set(align="left")
        printer.text("Task\n")
        wrapped_title = textwrap.wrap(title, width=CHARS_PER_LINE - SPECIAL_INDENT)
        for line in wrapped_title:
            printer.text(f"{' ' * SPECIAL_INDENT}{line}\n")
        printer.text("\n")
            
        # Due dates and target start dates
        labels_and_dates = [
            ("Planned start", planned_start if planned_start and planned_start.strip() else "—"),
            ("Due date", due_date if due_date and due_date.strip() else "—"),
        ]
        for label, value in labels_and_dates:
            printer.text(f"{label}{value.rjust(CHARS_PER_LINE - len(label))}\n")
        printer.text("\n")

        # Task description (wrap text if present)
        if description and description.strip():
            printer.text("Description\n")
            wrapped_description = textwrap.wrap(description, width=CHARS_PER_LINE - SPECIAL_INDENT)
            for line in wrapped_description:
                printer.text(f"{' ' * SPECIAL_INDENT}{line}\n")
            printer.text("\n")
            
        printer.set(align="center")
        printer.text("-" * CHARS_PER_LINE + "\n")

        # Optional handwritten notes block
        if PRINT_NOTES:
            printer.set(align="left")
            printer.text("Notes\n")
            for _ in range(PRINT_NOTES_LINES):
                printer.text("\n")
            printer.text("-" * CHARS_PER_LINE + "\n")

        # Append QR code linked to details/status update URL
        qr_data = f"{BASE_URL}/tasks/{id}"
        printer.set(align="center")
        printer.qr(qr_data, size=6)
        printer.text("Scan to mark as DONE\n\n")
        printer.text("-" * CHARS_PER_LINE + "\n\n")

        # Footer timestamp block
        printer.set(align="center")
        printer.text("Printed at\n")
        printer.text(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Paper cut and close connection
        printer.cut()
        printer.close()
        
        # Commit updated sequence number to database
        commit_receipt_number(number)
        print("✅ Task printed successfully!")
        return True

    except Exception as e:
        print("❌ Failed to print:", e)
        raise


def print_todo_summary_receipt(list_of_tasks: list) -> bool:
    """Connect to network printer and print a daily summary list of tasks.

    Args:
        list_of_tasks: List of task dictionaries.

    Returns:
        True if printing succeeds.
    """
    try:
        printer = Network(PRINTER_IP, PRINTER_PORT, timeout=10)
        printer.profile.profile_data["media"]["width"]["pixels"] = MEDIA_WIDTH_PIXELS

        # Main Header formatting
        printer._raw(b"\x1b\x40")       # Initialize printer
        printer._raw(b"\x1b\x45\x01")   # Bold on
        printer._raw(b"\x1b\x4d\x01")   # Emphasized mode on
        printer._raw(b"\x1d\x21\x11")   # Double size
        printer.set(align="center")
        printer.text("ToDo Summary\n")
        printer._raw(b"\x1d\x21\x10")   # Double height, normal width
        printer.text(f"{len(list_of_tasks)} {('tasks' if len(list_of_tasks) != 1 else 'task')}\n")
        printer._raw(b"\x1d\x21\x00")   # Reset size
        printer._raw(b"\x1b\x45\x00")   # Bold off
        printer._raw(b"\x1b\x4d\x00")   # Emphasized mode off
        printer.text("-" * CHARS_PER_LINE + "\n")

        # Loop through list and print list items
        for task in list_of_tasks:
            printer.set(align="left")
            wrapped_title = textwrap.wrap(task["title"], width=CHARS_PER_LINE - 2)
            for line in wrapped_title:
                if line == wrapped_title[0]:
                    printer.text(f"• {line}\n")
                else:
                    printer.text(f"{line}\n")
            if task["project"] and task["project"].strip():
                printer.text(f"  {task['project']}\n")
            if task["due_date"] and task["due_date"].strip():
                printer.text(f"  Due: {task['due_date']}\n")
            if task["priority"] and task["priority"].strip():
                printer.text(f"  Prio: {task['priority']}\n")
            if task["planned_start"] and task["planned_start"].strip():
                printer.text(f"  Start: {task['planned_start']}\n")
            if task != list_of_tasks[-1]:
                printer.text("\n")

        # Footer timestamp block
        printer.set(align="center")
        printer.text("-" * CHARS_PER_LINE + "\n")
        printer.text("Printed at\n")
        printer.text(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Paper cut and close connection
        printer.cut()
        printer.close()
        print("✅ ToDo summary printed successfully!")
        return True

    except Exception as e:
        print("❌ Failed to print:", e)
        raise
  

def print_logbook_receipt(target_date: str, list_of_logs: list) -> bool:
    """Print a list of logs recorded on the target date.

    Args:
        target_date: ISO date string of the log day.
        list_of_logs: List of parsed Notion log entries.

    Returns:
        True if printing succeeds.
    """
    try:
        printer = Network(PRINTER_IP, PRINTER_PORT, timeout=10)
        printer.profile.profile_data["media"]["width"]["pixels"] = MEDIA_WIDTH_PIXELS

        # Main Header formatting
        printer._raw(b"\x1b\x40")       # Initialize printer
        printer._raw(b"\x1b\x45\x01")   # Bold on
        printer._raw(b"\x1b\x4d\x01")   # Emphasized mode on
        printer._raw(b"\x1d\x21\x11")   # Double size
        printer.set(align="center")
        printer.text("Logbook\n")
        printer._raw(b"\x1d\x21\x10")   # Double height, normal width
        printer.text(f"{target_date} • {len(list_of_logs)} {('logs' if len(list_of_logs) != 1 else 'log')}\n")
        printer._raw(b"\x1d\x21\x00")   # Reset size
        printer._raw(b"\x1b\x45\x00")   # Bold off
        printer._raw(b"\x1b\x4d\x00")   # Emphasized mode off
        printer.text("-" * CHARS_PER_LINE + "\n")

        # Iterate and print log rows
        for log in list_of_logs:
            printer.set(align="left")
            
            # Format logs timestamp if present in the data record
            if log["logged_on"] and log["logged_on"].strip():
                logged_on = log["logged_on"].strip()
                try:
                    time_value = datetime.fromisoformat(logged_on).strftime("%H:%M")
                except ValueError:
                    time_value = logged_on  # Fallback to original value if parsing fails
                header_text = f"[{time_value}] {log['title']}"
            else:
                header_text = log["title"]
                
            wrapped_title = textwrap.wrap(header_text, width=CHARS_PER_LINE - 2)
            
            for line in wrapped_title:
                if line == wrapped_title[0]:
                    printer.text(f"• {line}\n")
                else:
                    printer.text(f"{line}\n")
                  
            if log["project"] and log["project"].strip():
                printer.text(f"  {log['project']}\n")
                
            if log["log"] and log["log"].strip():
                wrapped_log = textwrap.wrap(log["log"], width=CHARS_PER_LINE - SPECIAL_INDENT)
                for line in wrapped_log:
                    printer.text(f"{' ' * SPECIAL_INDENT}{line}\n")
                  
            if log != list_of_logs[-1]:
                printer.text("\n")

        # Footer timestamp block
        printer.set(align="center")
        printer.text("-" * CHARS_PER_LINE + "\n")
        printer.text("Printed at\n")
        printer.text(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Paper cut and close connection
        printer.cut()
        printer.close()
        print("✅ Logbook printed successfully!")
        return True

    except Exception as e:
        print("❌ Failed to print:", e)
        raise


if __name__ == "__main__":
    # Test execution sample data
    print_todo_summary_receipt([
        {
            "id": "task1",
            "project": "Project Alpha",
            "priority": "High",
            "title": "[AP] Special financial knowledge workshop so fun to attend",
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