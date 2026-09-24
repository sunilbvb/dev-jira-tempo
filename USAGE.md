# How to Use tempo-log: Step-by-Step Guide & Real Examples

This guide walks you through every way to use **`tempo-log`**, from everyday command-line workflows to integrating it inside custom applications.

---

## 📖 Table of Contents

1. [Daily Developer CLI Workflow](#1-daily-developer-cli-workflow)
2. [Handling Past or Missed Time Entries](#2-handling-past-or-missed-time-entries)
3. [Batch Submissions (End of Week Logging)](#3-batch-submissions-end-of-week-logging)
4. [Fixing Mistakes with `update`](#4-fixing-mistakes-with-update)
5. [Auditing Your Work with the Local Journal](#5-auditing-your-work-with-the-local-journal)
6. [Speed Tips: Shell Aliases & Productivity Shortcuts](#6-speed-tips-shell-aliases--productivity-shortcuts)
7. [Integrating tempo-log in Other Apps (Python SDK)](#7-integrating-tempo-log-in-other-apps-python-sdk)
8. [Common Error Messages & How to Fix Them](#8-common-error-messages--how-to-fix-them)

---

## 1. Daily Developer CLI Workflow

### Morning: Check Your Setup
When starting your day, run `doctor` to make sure your connection and tokens are active:
```bash
tempo-log doctor
```
Expected output:
```text
Tempo: OK (TEMPO_API_TOKEN authenticates).
Jira: OK (authenticated as accountId=557058:abc-123).
JIRA_ACCOUNT_ID: set (557058:abc-123).
```

### Midday: Log Work as You Complete Tasks
Whenever you finish a task, log it directly:
```bash
tempo-log create --issue PROJ-101 --hours 1.5 --description "Implemented password reset email"
```
Output:
```text
Logged 1.5h on issue 10052. Tempo worklog ID: 49102
```

### Evening: Review Today's Work
At the end of the day, list what you logged:
```bash
tempo-log list --from 2026-09-24 --to 2026-09-24
```

---

## 2. Handling Past or Missed Time Entries

If you forgot to log hours for yesterday or earlier this week, pass `--date` and optionally `--time`:

### Example: Log 3.5 hours for yesterday
```bash
tempo-log create --issue PROJ-204 --hours 3.5 --date 2026-09-23 --description "Database indexing and performance tuning"
```

### Example: Log with specific start time
```bash
tempo-log create --issue PROJ-105 --hours 1.0 --date 2026-09-23 --time 14:00:00 --description "Sprint retrospective"
```

---

## 3. Batch Submissions (End of Week Logging)

If you prefer logging all your hours at once on Friday afternoon, create a JSON file:

### Step 1: Create your timesheet file (e.g. `friday.json`)
```json
[
  {
    "issue": "PROJ-101",
    "hours": 4.0,
    "date": "2026-09-22",
    "description": "Auth module unit tests"
  },
  {
    "issue": "PROJ-102",
    "hours": 3.5,
    "date": "2026-09-23",
    "description": "API swagger documentation"
  },
  {
    "issue": "PROJ-105",
    "hours": 2.0,
    "date": "2026-09-24",
    "description": "Sprint planning and refinement"
  }
]
```

*(You can also use the sample file located at [`examples/batch_timesheet_sample.json`](examples/batch_timesheet_sample.json)).*

### Step 2: Upload the batch
```bash
tempo-log batch friday.json
```
Output:
```text
3 succeeded, 0 failed.
Journal: /home/your-user/.tempo-log/journal.jsonl
```

---

## 4. Fixing Mistakes with `update`

Made a typo or logged the wrong hours? You do **not** need to open a browser to fix it.

1. Find the `tempoWorklogId` using `tempo-log list`:
   ```bash
   tempo-log list --from 2026-09-24 --to 2026-09-24
   ```
2. Update the hours or description:
   ```bash
   tempo-log update 49102 --hours 2.0 --description "Implemented password reset email and SMS"
   ```
Output:
```text
Updated worklog 49102.
```

---

## 5. Auditing Your Work with the Local Journal

Every time you create a worklog, `tempo-log` automatically appends an audit record to your local machine at:
`~/.tempo-log/journal.jsonl`

### View your local history:
```bash
cat ~/.tempo-log/journal.jsonl | tail -n 5
```

Each line contains a complete JSON record with exact timestamps:
```json
{"tempoWorklogId": 49102, "issueId": 10052, "accountId": "557058:abc-123", "hours": 1.5, "startDate": "2026-09-24", "startTime": "10:00:00", "description": "Implemented password reset email", "loggedAt": "2026-09-24T10:00:05.123456+00:00"}
```

---

## 6. Speed Tips: Shell Aliases & Productivity Shortcuts

Add these handy shortcuts to your `~/.bashrc` or `~/.zshrc`:

```bash
# Log time fast
alias tlog="tempo-log create"

# Check today's logged hours
alias ttoday="tempo-log list --from $(date +%Y-%m-%d) --to $(date +%Y-%m-%d)"

# Run connection doctor
alias tdoc="tempo-log doctor"
```

Now you can log time in 3 seconds:
```bash
tlog --issue PROJ-101 --hours 1.5 --description "Bug fixing"
ttoday
```

---

## 7. Integrating tempo-log in Other Apps (Python SDK)

If you are developing a **Slack Bot**, a **Flask/FastAPI web dashboard**, or a **CLI helper**, import `tempo_log` directly:

```python
from tempo_log import TempoService, JiraConfig, MemoryJournal

# Setup the engine
service = TempoService(
    tempo_token="YOUR_TEMPO_TOKEN",
    jira_config=JiraConfig(
        base_url="https://company.atlassian.net",
        email="dev@company.com",
        api_token="YOUR_JIRA_API_TOKEN",
    ),
    journal=MemoryJournal(), # In-memory journal for server environments
)

# Call from a Slack slash command or web API route:
def handle_slack_time_command(user_slack_id, issue_key, hours, notes):
    try:
        worklog = service.log_time(
            issue=issue_key,
            hours=float(hours),
            description=notes,
        )
        return f"Logged {hours}h to {issue_key}. ID: {worklog['tempoWorklogId']}"
    except Exception as error:
        return f"Error logging time: {error}"
```

*(See [`examples/sdk_usage.py`](examples/sdk_usage.py) for a complete runnable script).*

---

## 8. Common Error Messages & How to Fix Them

### Error 1: `ERROR: TEMPO_API_TOKEN environment variable is not set.`
- **Reason**: The tool cannot find your Tempo token.
- **Fix**: Run `export $(grep -v '^#' .env | xargs)` or check that `.env` has `TEMPO_API_TOKEN=...`.

### Error 2: `Failed to resolve issue 'PROJ-123': 404 Issue does not exist`
- **Reason**: The Jira issue key is mistyped, or your Jira API token cannot access this Jira project.
- **Fix**: Verify the issue key in your browser.

### Error 3: `401 Unauthorized`
- **Reason**: Token is expired or incorrect.
- **Fix**: Generate a fresh token in Tempo (**Tempo -> Settings -> API Integration -> New Token**).
