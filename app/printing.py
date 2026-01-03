import os
import textwrap
from dotenv import load_dotenv
from escpos.printer import Network
from datetime import datetime

load_dotenv()

PRINTER_IP = os.getenv("PRINTER_IP")
PRINTER_PORT = int(os.getenv("PRINTER_PORT", 9100))
PAPER_WIDTH_MM = int(os.getenv("PAPER_WIDTH_MM", 80))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SPECIAL_INDENT = int(os.getenv("SPECIAL_INDENT", 4))
  
PIXELS_MAP = {58: 384, 80: 576}
MEDIA_WIDTH = PIXELS_MAP.get(PAPER_WIDTH_MM, 576)

CHARS_PER_LINE_MAP = {58: 32, 80: 48}
CHARS_PER_LINE = CHARS_PER_LINE_MAP.get(PAPER_WIDTH_MM, 48)

if not PRINTER_IP:
    raise ValueError("PRINTER_IP is not set in .env!")

def print_task_receipt(id: str, project: str, priority: str, title: str, created_at: str, planned_for: str, due_date: str, description: str):
  """Print a task receipt.

  Args:
      id (str): The ID of the task.
      project (str): The project of the task.
      priority (str): The priority of the task.
      title (str): The title of the task.
      created_at (str): The creation date of the task.
      planned_for (str): The planned date for the task.
      due_date (str): The due date of the task.
      description (str): The description of the task.
  """
  try:
    printer = Network(PRINTER_IP, PRINTER_PORT, media_width=MEDIA_WIDTH, timeout=10)

    # MAIN HEADER: Project
    printer._raw(b'\x1b\x40')  # ESC/POS command to initialize printer
    printer._raw(b'\x1d\x21\x11')  # ESC/POS command for double width and height
    printer._raw(b'\x1b\x45\x01')  # ESC/POS command for bold on
    printer._raw(b'\x1b\x4d\x01') # ESC/POS command for emphasized mode on
    printer.set(align='center')
    printer.text(f"{project}\n")

    # SECONDARY HEADER: Priority
    printer.set(align='center')
    printer.text(f"Priority: {priority}\n\n")
    printer._raw(b'\x1d\x21\x00') # ESC/POS command for normal size
    printer._raw(b'\x1b\x45\x00')  # ESC/POS command for bold off
    printer._raw(b'\x1b\x4d\x00') # ESC/POS command for emphasized mode off
    printer.text("-" * (PAPER_WIDTH_MM // 2) + "\n\n")

    # TASK
    printer.set(align='left')
    printer.text(f"Task\n")
    wrapped_title = textwrap.wrap(title, width=CHARS_PER_LINE - SPECIAL_INDENT)
    for line in wrapped_title:
      printer.text(f"{' ' * SPECIAL_INDENT}{line}\n")
    printer.text("\n")
        
    # DATES
    labels_and_dates = [
        ("Created at", created_at),
        ("Planned for", planned_for),
        ("Due date", due_date),
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
      printer.text("-" * (PAPER_WIDTH_MM // 2) + "\n")
      
    # QR
    qr_data = f"{BASE_URL}/tasks/{id}"
    printer.set(align='center')
    printer.qr(qr_data, size=6)
    printer.text("Scan to mark as DONE\n\n")
    printer.text("-" * (PAPER_WIDTH_MM // 2) + "\n\n")

    # FOOTER: print timestamp
    printer.set(align='center')
    printer.text(f"Printed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # CUT
    printer.cut()
    printer.close()
    print("✅ Task printed successfully!")

  except Exception as e:
      print("❌ Failed to print:", e)
  
    
if __name__ == "__main__":
  print_task_receipt("12345", "Example Project", "High", "Example Task", "2026-01-01", "2026-01-02", "2026-01-03", "This is an example task description that is a little long and needs to be wrapped properly.")