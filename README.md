# Oral History of Computer Science

A Python project that organizes computing-history excerpts into annotated
MEDFORD records and an HTML report.

## Before you start

Install **Python 3.12 or newer** and **Git**. Open a terminal in the
`cs-oral-history` folder, where `run_sample.py` and `requirements.txt` are located.

Download each dependency below **only if its folder is missing**. These Git
commands work on both macOS and Windows:

```bash
git clone https://github.com/TuftsBCB/medford libraries/medford
git clone --depth 1 https://github.com/brownhci/drafty libraries/drafty
```

Create the Python environment separately on each computer; do not copy `.venv/`
between macOS and Windows. Skip the environment-creation command if you already
have a working local `.venv/`.

## Run on macOS

In Terminal:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python run_sample.py
.venv/bin/python -m ohcs.report

open out/report.html
```

## Run on Windows

In PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\.venv\Scripts\python.exe run_sample.py
.\.venv\Scripts\python.exe -m ohcs.report

Start-Process ./out/report.html
```

These commands use the environment's Python directly, so activation is not
required. On later runs, skip environment creation and dependency installation;
run the two project commands and open the report. In each new Windows
PowerShell session, set `PYTHONUTF8` as shown above before running the project.

The sample writes annotated files to `out/medford/` and analysis results to
`out/results.json`. The report command then generates `out/report.html`.
Without a `TYPESAFE_API_KEY` environment variable, extraction uses an offline
keyword stub instead of live Jev. To view the existing saved report without
running anything, open `out/report.html` in a browser.

## General structure

```text
cs-oral-history/
├── README.md              Setup and run instructions
├── requirements.txt       Python dependencies
├── .gitignore             Files excluded from Git
├── run_sample.py          Entry point for the sample pipeline
├── ohcs/                  Project code: collection, extraction, analysis, reports
├── data/                  Curated excerpts and theme codebook
├── schema/                Custom MEDFORD validation rules
├── out/                   Generated HTML, analysis JSON, and MEDFORD records
├── docs/                  Project notes and completed-work inventory
├── libraries/             Third-party code and datasets
│   ├── medford/           External metadata parser and its tests/examples
│   └── drafty/            External faculty dataset, downloaded during setup
└── .venv/                 Local Python environment and installed packages
```

**Work mainly in `ohcs/`, `data/`, and `schema/`.** The code under `libraries/`
belongs to external projects. View generated results in `out/`; change the
inputs or project code when you want to change those results.
