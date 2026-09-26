# tempo-log (dev-jira-tempo)

[![CI](https://github.com/sunilbvb/dev-jira-tempo/actions/workflows/ci.yml/badge.svg)](https://github.com/sunilbvb/dev-jira-tempo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

> **A fast, simple tool to log work time to Tempo (Jira) directly from your terminal or Python code.**

---

## 📌 Table of Contents

- [What is this?](#-what-is-this)
- [Why use it?](#-why-use-it)
- [How it Works](#-how-it-works)
- [Quick Start (3 Easy Steps)](#-quick-start-3-easy-steps)
- [Configuration (.env)](#-configuration-env)
- [CLI Usage Guide](#-cli-usage-guide)
  - [1. Check connection (`doctor`)](#1-check-connection-doctor)
  - [2. Log time (`create`)](#2-log-time-create)
  - [3. View worklogs (`list`)](#3-view-worklogs-list)
  - [4. Edit a worklog (`update`)](#4-edit-a-worklog-update)
  - [5. Batch upload from file (`batch`)](#5-batch-upload-from-file-batch)
- [Python SDK Guide (Use in Your Own Apps)](#-python-sdk-guide-use-in-your-own-apps)
- [📖 Detailed How-To Guide & Scenarios (USAGE.md)](USAGE.md)
- [🤝 Contributing Guide & Roadmap (CONTRIBUTING.md)](CONTRIBUTING.md)
- [🗂️ Project File Map & Line Index (FILES.md)](FILES.md)
- [Frequently Asked Questions (FAQ)](#-frequently-asked-questions-faq)
- [Testing](#-testing)
- [License](#-license)

---

## 💡 What is this?

If your team uses **Jira** and **Tempo Timesheets**, you normally have to open a browser, click through multiple pages, and wait for slow web forms just to log a few hours of work.

**`tempo-log` makes this instant.**
You can log time with a single terminal command like:
```bash
tempo-log create --issue PROJ-123 --hours 2.5 --description "Bug fixing"
```

It is also built as a **reusable Python library**, meaning you can import it into your own Slack bots, web apps, or automation scripts.

---

## ✨ Why use it?

- **Fast & Simple**: One command logs your hours in 1 second.
- **Human-Friendly**: Use issue names like `PROJ-123`—the tool automatically finds the internal numeric ID for you.
- **Offline Journal**: Saves a copy of all logged hours in a local file (`~/.tempo-log/journal.jsonl`) so you never lose your history.
- **Batch Upload**: Log hours for an entire week at once using a simple JSON file.
- **Developer Ready**: Clean Python SDK with zero bloat (only requires the standard `requests` package).

---

## 🏗️ How it Works

```text
                     ┌───────────────────────────┐
                     │   Your Terminal (CLI)     │
                     │           OR              │
                     │  Your App (Slack/Web/Bot) │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │       TempoService        │
                     │  (Main Python Engine/SDK) │
                     └──────┬─────────────┬──────┘
                            │             │
              ┌─────────────┘             └─────────────┐
              ▼                                         ▼
   ┌──────────────────────┐                  ┌──────────────────────┐
   │      JiraClient      │                  │     TempoClient      │
   │ Resolves "PROJ-123"  │                  │ Creates & updates    │
   │ to numeric issue ID  │                  │ official worklogs    │
   └──────────┬───────────┘                  └──────────┬───────────┘
              ▼                                         ▼
     Atlassian Cloud API                         Tempo REST API
```

---

## 🚀 Quick Start (3 Easy Steps)

### Step 1: Install

#### Option A: Recommended for daily CLI use (via `pipx`)
[pipx](https://pypa.github.io/pipx/) installs the command globally in an isolated environment so it is always available:
```bash
pipx install git+https://github.com/sunilbvb/dev-jira-tempo.git
```

#### Option B: For developers (standard Python virtual environment)
```bash
git clone https://github.com/sunilbvb/dev-jira-tempo.git
cd dev-jira-tempo
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

### Step 2: Configure Your Keys

1. Copy the example file to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` in any text editor and fill in your keys:
   ```bash
   # Required:
   TEMPO_API_TOKEN=your_tempo_token_here

   # Optional (Required only if you want to use issue keys like PROJ-123):
   JIRA_BASE_URL=https://yourcompany.atlassian.net
   JIRA_EMAIL=you@company.com
   JIRA_API_TOKEN=your_jira_token_here
   ```
3. Load the variables:
   ```bash
   export $(grep -v '^#' .env | xargs)
   ```

---

### Step 3: Test and Log Time!

Test that your credentials work:
```bash
tempo-log doctor
```

Log your first worklog:
```bash
tempo-log create --issue PROJ-123 --hours 2 --description "Initial project setup"
```

---

## ⚙️ Configuration (.env)

| Variable | Required? | Example | Where to find it? |
|---|:---:|---|---|
| `TEMPO_API_TOKEN` | **Yes** | `t-abc12345...` | In Jira: **Tempo** -> **Settings** -> **API Integration** -> **New Token**. |
| `JIRA_BASE_URL` | Optional | `https://myco.atlassian.net` | The web address you use to open Jira in your browser. |
| `JIRA_EMAIL` | Optional | `alex@company.com` | The email address you use to log into Jira. |
| `JIRA_API_TOKEN` | Optional | `ATATT3...` | Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens) and click **Create API token**. |
| `JIRA_ACCOUNT_ID` | Optional | `557058:9182...` | Your Jira user account ID. (If left blank, the tool detects it automatically). |
| `TEMPO_LOG_JOURNAL` | Optional | `/path/to/log.jsonl` | Custom file path for the local audit log. Defaults to `~/.tempo-log/journal.jsonl`. |

---

## 💻 CLI Usage Guide

### 1. Check connection (`doctor`)
Runs a quick health check to verify that your Tempo and Jira tokens are valid:
```bash
tempo-log doctor
```
**Example Output:**
```text
Tempo: OK (TEMPO_API_TOKEN authenticates).
Jira: OK (authenticated as accountId=557058:abc-123).
JIRA_ACCOUNT_ID: set (557058:abc-123).
```

---

### 2. Log time (`create`)

#### Basic: Log time using issue name
```bash
tempo-log create --issue PROJ-123 --hours 2.5 --description "Refactored login module"
```

#### With specific date and time
If you forgot to log hours yesterday:
```bash
tempo-log create --issue PROJ-123 --hours 4.0 --date 2026-09-23 --time 09:30:00 --description "Client meeting & planning"
```

#### Fast: Log with numeric ID (skips Jira lookup)
```bash
tempo-log create --issue-id 10042 --hours 1.0 --description "Quick standup"
```

---

### 3. View worklogs (`list`)

List all worklogs you logged between two dates:
```bash
tempo-log list --from 2026-09-01 --to 2026-09-24
```

**Example Output:**
```text
34891   2026-09-24 09:30:00   issue=10042   2.5h   Refactored login module
34892   2026-09-24 14:00:00   issue=10080   1.5h   Code review

2 worklog(s) shown (limit=50, offset=0).
```

---

### 4. Edit a worklog (`update`)

Fix hours or typo in description on an existing worklog ID (e.g. ID `34891`):
```bash
tempo-log update 34891 --hours 3.0 --description "Refactored login module and added tests"
```

---

### 5. Batch upload from file (`batch`)

Log an entire day or week in one go using a simple JSON file:
```bash
tempo-log batch my-timesheet.json
```

If you want the command to stop immediately if one entry fails:
```bash
tempo-log batch my-timesheet.json --stop-on-error
```

#### Example `my-timesheet.json`
```json
[
  {
    "issue": "PROJ-123",
    "hours": 3.5,
    "date": "2026-09-24",
    "description": "API development"
  },
  {
    "issue": "PROJ-456",
    "hours": 1.0,
    "date": "2026-09-24",
    "time": "14:00:00",
    "description": "Sprint backlog grooming"
  }
]
```

---

### 6. Live Stopwatch / Timer Mode (`start`, `status`, `stop`)

Track time dynamically as you work:
```bash
# Start a timer
tempo-log start --issue PROJ-123 --desc "Debugging memory leak"

# Check active timer status & elapsed duration
tempo-log status

# Stop timer and immediately log to Tempo
tempo-log stop

# Or discard active timer without logging
tempo-log stop --discard
```

---

### 7. Interactive TUI Dashboard (`tui`)

Launch an interactive terminal dashboard displaying active timers, today's work, weekly progress against targets, and keyboard shortcuts:
```bash
# Interactive live loop
tempo-log tui

# Or snapshot mode (print once and exit)
tempo-log tui --once
```

---

### 8. Weekly Summary & SQLite Audit Backend (`summary`)

Aggregates daily totals, issues breakdown, and exports to CSV:
```bash
# View summary table and recent audit entries
tempo-log summary

# Export complete worklog audit history to CSV
tempo-log summary --export-csv timesheet_export.csv
```

---

### 9. OS Keyring Secret Storage (`auth`)

Securely store tokens in macOS Keychain, Linux Secret Service, or Windows Credential Vault instead of keeping plaintext tokens in `.env`:
```bash
# Store Tempo API token
tempo-log auth set-token tempo "your-tempo-token"

# Store Jira API token
tempo-log auth set-token jira "your-jira-token"

# Check keyring backend status
tempo-log auth status
```

---

### 10. Shell Tab-Completion (`completion`)

Generate autocompletion scripts with dynamic issue key suggestions:
```bash
# Bash completion
tempo-log completion --shell bash > ~/.tempo-log-completion.bash
echo "source ~/.tempo-log-completion.bash" >> ~/.bashrc

# Zsh completion
tempo-log completion --shell zsh > ~/.zfunc/_tempo-log

# Fish completion
tempo-log completion --shell fish > ~/.config/fish/completions/tempo-log.fish
```

---

### 11. Git Commit Auto-Worklog Hook (`git-hook`)

Automatically log work whenever you commit code matching patterns like `PROJ-123: 1.5h - Description` or `#time 1h`:
```bash
# Install hook into current Git repository (.git/hooks/post-commit)
tempo-log git-hook install

# Dry-run test a commit message string
tempo-log git-hook check "PROJ-123: 1.5h - Fix login redirect bug"

# Uninstall hook
tempo-log git-hook uninstall
```

---

### 12. Jira Server & Data Center (On-Premise)

For Jira Server or Data Center with Personal Access Tokens (PAT):
```bash
export JIRA_BASE_URL="https://jira.internal.corp"
export JIRA_API_TOKEN="your-personal-access-token"
export JIRA_SERVER=true
```
The client automatically switches to Bearer PAT authentication and Jira API v2 endpoints.

---

## 🐍 Python SDK Guide (Use in Your Own Apps)

You can import `tempo_log` directly into your own projects (e.g., Slack bot, FastAPI service, Raycast script):

```python
from tempo_log import TempoService, JiraConfig, Settings, MemoryJournal

# 1. Initialize the service
service = TempoService(
    tempo_token="your-tempo-token",
    jira_config=JiraConfig(
        base_url="https://yourcompany.atlassian.net",
        email="you@company.com",
        api_token="your-jira-token",
    ),
    # Optional: use MemoryJournal() in servers or unit tests to avoid disk files
    journal=MemoryJournal(),
)

# 2. Log work in a single function call
# Resolves issue key, checks user account, submits to Tempo, and records to journal:
result = service.log_time(
    issue="PROJ-123",
    hours=2.5,
    description="Implemented payment webhook",
)

print("Created Worklog ID:", result["tempoWorklogId"])

# 3. Read worklogs
recent_logs = service.list_time(from_date="2026-09-01", to_date="2026-09-24")

# 4. Update worklog
service.update_time(worklog_id=12345, hours=3.0)
```

### Pluggable Journal Types
Choose where your logs are saved:
- `FileJournal()`: Appends to a local JSONL file (default).
- `MemoryJournal()`: Keeps records in Python memory (great for web servers or unit tests).
- `NullJournal()`: Discards history (if you do not need audit logs).

---

## ❓ Frequently Asked Questions (FAQ)

<details>
<summary><b>1. Do I need Jira API credentials?</b></summary>
<p>
Only if you want to use issue names like <code>PROJ-123</code>. If you provide the numeric issue ID (e.g. <code>--issue-id 10042</code>) and your Jira account ID, only <code>TEMPO_API_TOKEN</code> is required.
</p>
</details>

<details>
<summary><b>2. Where is my local history saved?</b></summary>
<p>
All created worklogs are saved to <code>~/.tempo-log/journal.jsonl</code> as JSON lines. You can change this location by setting <code>TEMPO_LOG_JOURNAL=/custom/path.jsonl</code>.
</p>
</details>

<details>
<summary><b>3. Why do I get a 401 Unauthorized error?</b></summary>
<p>
Make sure your <code>TEMPO_API_TOKEN</code> has not expired in Tempo. If the error mentions Jira, check that your Atlassian API token matches the email address in <code>JIRA_EMAIL</code>.
</p>
</details>

<details>
<summary><b>4. Does this support Jira Server / On-Premise?</b></summary>
<p>
Yes! Jira Server and Data Center on-premise deployments are supported via Personal Access Token (PAT) authentication. Simply set <code>JIRA_SERVER=true</code> or omit <code>JIRA_EMAIL</code>.
</p>
</details>

---

## 🧪 Testing

To run the automated test suite:

```bash
pytest -v
```

All 63 unit tests mock external network requests, so they run in less than **0.4 seconds** without needing real API tokens.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
