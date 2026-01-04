# SC Task Receipts
This repository contains the source code for the `sc-task-receipts` package.

## Environment Variables
The following environment variables can be set to configure the package:

| Variable | Purpose | Example |
|---|---|---|
| `NOTION_TOKEN` | Notion integration token used to authenticate API requests | `secret_xxx` |
| `NOTION_TASKS_ID` | Notion database/data_source ID containing tasks | `xxxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `NOTION_PROJECTS_ID` | Notion database/data_source ID containing projects | `xxxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `NOTION_PRINT_TAG` | Property name used to mark printed tasks | `Printed` |
| `BASE_URL` | Base URL of the running app (used in links) | `http://localhost:8000` |
| `PRINTER_IP` | IP address of the network printer | `127.0.0.1` |
| `PRINTER_PORT` | Port of the network printer | `9100` |
| `PAPER_WIDTH_MM` | Paper width in millimetres for receipts | `80` |
| `SPECIAL_INDENT` | Optional indentation for printed receipts | `4` |
| `RECEIPT_NUMBER_RESET_AT` | Number at which the receipt number resets to 1 | `99` |
| `DB_PATH` | Path to the SQLite database file for counters (creates its own file if missing) | `~/data/counters.sqlite3` |

## Installation
To install the package, run:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

## Running
To run the application enter `src` and execute:
```bash
uvicorn sc_task_receipts.main:app --reload --host 127.0.0.1 --port 8000
```

Also, make sure to set the required environment variables before running the application, especially that `--host` and `--port` match the `BASE_URL` configuration.