# tempo-log (dev-jira-tempo)

[![CI](https://github.com/sunil-bakale/dev-jira-tempo/actions/workflows/ci.yml/badge.svg)](https://github.com/sunil-bakale/dev-jira-tempo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Fast, standalone CLI tool for logging work hours to [Tempo Timesheets](https://www.tempo.io/) for Jira Cloud.

Avoid slow web UI clicks—log, list, update, and batch-upload time entries straight from your terminal.

---

## Features

- ⚡ **Instant time logging**: Log time in seconds using Jira issue keys (e.g., `PROJ-123`) or numeric IDs.
- 🩺 **Doctor command**: Quickly verify Tempo and Jira credentials and permissions.
- 📦 **Batch submissions**: Submit days or weeks of worklogs at once via a simple JSON file.
- 📓 **Local audit journal**: Automatically records all created entries to `~/.tempo-log/journal.jsonl`.
- 🔍 **List & update**: Review your logged worklogs and adjust hours or descriptions on the fly.
- 🪶 **Zero bloat**: Lightweight, minimal dependencies (`requests` only).

---

## Installation

### Recommended: Install via [pipx](https://pypa.github.io/pipx/) (Isolated CLI app)

```bash
pipx install git+https://github.com/sunil-bakale/dev-jira-tempo.git
```

### Local Development / pip

```bash
git clone https://github.com/sunil-bakale/dev-jira-tempo.git
cd dev-jira-tempo
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Configuration

Copy `.env.example` to `.env` and fill in credentials:

```bash
cp .env.example .env
export $(grep -v '^#' .env | xargs)
```

*(Tip: You can use [direnv](https://direnv.net/) to auto-load `.env` when entering the directory).*

### Environment Variables

| Variable | Required | Description |
|---|:---:|---|
| `TEMPO_API_TOKEN` | **Yes** | Tempo -> Settings -> API Integration -> New Token |
| `JIRA_BASE_URL` | Optional | e.g. `https://yourcompany.atlassian.net` (for issue key resolution) |
| `JIRA_EMAIL` | Optional | Jira user email address |
| `JIRA_API_TOKEN` | Optional | Atlassian API token (Account Settings -> Security -> Create token) |
| `JIRA_ACCOUNT_ID` | Optional | Your Jira `accountId` (skips auto-detection / required if no Jira token) |
| `TEMPO_LOG_JOURNAL` | Optional | Custom path for audit log (defaults to `~/.tempo-log/journal.jsonl`) |

---

## Commands & Usage

### 1. Verify Setup (`doctor`)

Check your connection and credential health:

```bash
tempo-log doctor
```

Output:
```text
Tempo: OK (TEMPO_API_TOKEN authenticates).
Jira: OK (authenticated as accountId=557058:abc-123).
JIRA_ACCOUNT_ID: set (557058:abc-123).
```

### 2. Log Work (`create`)

Log by Jira issue key:
```bash
tempo-log create --issue PROJ-123 --hours 2.5 --description "Backend API refactor"
```

Log by numeric issue ID and custom start time/date:
```bash
tempo-log create --issue-id 10042 --hours 1.0 --date 2026-09-24 --time 09:30:00 --description "Standup & sync"
```

### 3. List Worklogs (`list`)

List worklogs for your account within a date window:
```bash
tempo-log list --from 2026-09-01 --to 2026-09-24
```

### 4. Update Existing Worklog (`update`)

Update logged hours or description:
```bash
tempo-log update 25234 --hours 3.0 --description "Updated description after review"
```

### 5. Batch Upload (`batch`)

Log multiple entries from a JSON file:

```bash
tempo-log batch worklogs.json
```

Add `--stop-on-error` to abort if an entry fails:
```bash
tempo-log batch worklogs.json --stop-on-error
```

#### Batch JSON Format

```json
[
  {
    "issue": "PROJ-123",
    "hours": 3.0,
    "date": "2026-09-24",
    "description": "Feature implementation"
  },
  {
    "issue_id": 10042,
    "hours": 1.5,
    "date": "2026-09-24",
    "time": "14:00:00",
    "description": "Code review & bug fixes"
  }
]
```

---

## Running Tests

Run test suite:

```bash
pytest
```

---

## License

This project is licensed under the [MIT License](LICENSE).
