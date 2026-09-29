# Frequently Asked Questions (FAQ) — tempo-log

Comprehensive answers to common questions about configuration, credentials, session journal analysis, timesheet submission, and troubleshooting.

---

## 📌 Table of Contents

- [General & Authentication](#-general--authentication)
  - [1. Do I need Jira API credentials?](#1-do-i-need-jira-api-credentials)
  - [2. Where are my credentials stored?](#2-where-are-my-credentials-stored)
  - [3. Where is my local history saved?](#3-where-is-my-local-history-saved)
  - [4. Why do I get a 401 Unauthorized error?](#4-why-do-i-get-a-401-unauthorized-error)
  - [5. Does this support Jira Server / On-Premise?](#5-does-this-support-jira-server--on-premise)
- [Session Journal Analysis (`analyze`)](#-session-journal-analysis-analyze)
  - [6. What is the session journal analyzer?](#6-what-is-the-session-journal-analyzer)
  - [7. How does direct submission work (`--submit`)?](#7-how-does-direct-submission-work---submit)
  - [8. How does automatic duplicate skipping work?](#8-how-does-automatic-duplicate-skipping-work)
  - [9. How does entry consolidation work (`--consolidate`)?](#9-how-does-entry-consolidation-work---consolidate)
  - [10. How are meetings handled without a ticket?](#10-how-are-meetings-handled-without-a-ticket)
  - [11. How are timesheet descriptions cleaned?](#11-how-are-timesheet-descriptions-cleaned)
  - [12. What if my journal timestamps record when work ended?](#12-what-if-my-journal-timestamps-record-when-work-ended)
  - [13. How do fixed blocks (like lunch) work?](#13-how-do-fixed-blocks-like-lunch-work)
  - [14. Can I map keywords to tickets automatically?](#14-can-i-map-keywords-to-tickets-automatically)

---

## 🔑 General & Authentication

### 1. Do I need Jira API credentials?
Only if you want `tempo-log` to resolve human-readable issue keys like `PROJ-123` to numeric issue IDs automatically.
If you provide numeric issue IDs (e.g. `[id:10042]` in your journal or `--issue-id 10042` in CLI) and set `JIRA_ACCOUNT_ID`, you only need `TEMPO_API_TOKEN`.

### 2. Where are my credentials stored?
You can store credentials in three ways:
1. **OS Keyring** (Recommended): Run `tempo-log auth set-token tempo <TOKEN>` and `tempo-log auth set-token jira <TOKEN>`.
2. **Local `.env` file**: Located in your project root or `~/.tempo-log/.env`.
3. **Environment variables**: Standard shell environment (`export TEMPO_API_TOKEN=...`).

### 3. Where is my local history saved?
All created worklogs are recorded locally in `~/.tempo-log/journal.jsonl` (and optionally in SQLite if configured). You can customize this with `TEMPO_LOG_JOURNAL=/path/to/journal.jsonl`.

### 4. Why do I get a 401 Unauthorized error?
- **Tempo**: Generate a fresh API token in Tempo via **Tempo -> Settings -> API Integration -> New Token**.
- **Jira Cloud**: Check that `JIRA_EMAIL` matches the email of your Atlassian API token.
- **Jira Server / DC**: Ensure your Personal Access Token (PAT) is active and `JIRA_SERVER=true` (or `JIRA_EMAIL` omitted).

### 5. Does this support Jira Server / On-Premise?
Yes. Both Jira Server and Data Center deployments are supported via Personal Access Tokens (PAT). Set `JIRA_SERVER=true` and provide your PAT in `JIRA_API_TOKEN`.

---

## 📝 Session Journal Analysis (`analyze`)

### 6. What is the session journal analyzer?
`tempo-log analyze` parses free-form session journals written during the day (by developers or AI coding assistants) and turns them into clean, valid timesheet proposals.
It automatically calculates durations, snaps start times, rounds entries, cleans bullet points, checks daily hour caps, and identifies blockers before anything touches Tempo.

### 7. How does direct submission work (`--submit`)?
Running `tempo-log analyze journal.md --date today --submit` performs a full safety check:
1. Re-fetches the day's existing worklogs from Tempo.
2. Skips anything already logged (marked `LOGGED (#id)`).
3. Validates that no remaining entries are `BLOCKED`.
4. Shows the final upload plan and asks for confirmation (`Upload N entries? [y/N]`).
5. Uploads the worklogs. If any entry fails, it immediately rolls back all worklogs created during the run so your timesheet never stays in a broken state.
Use `--yes` (or `-y`) to skip the confirmation prompt for automated scripts.

### 8. How does automatic duplicate skipping work?
The analyzer matches planned journal entries against existing Tempo worklogs by matching the issue and checking for overlapping time windows (or matching start times within `TEMPO_DUPLICATE_WINDOW_MINUTES`, default 15 minutes).
Matched entries receive status `LOGGED (#<worklog_id>)` and are never submitted again.

### 9. How does entry consolidation work (`--consolidate`)?
When you log multiple small sessions throughout the day on the same ticket:
- `--consolidate` (or `--consolidate contiguous`): Merges consecutive entries on the same ticket.
- `--consolidate day`: Merges all entries on the same ticket across the entire day.
Minutes are summed *before* rounding (preventing seven 5-minute entries from inflating into 1h45m), and bullet points are combined and de-duplicated.

### 10. How are meetings handled without a ticket?
Headings starting with `Meeting:` (configurable via `TEMPO_MEETING_PREFIX`) automatically use `TEMPO_MEETING_ISSUE` (or `--meeting-issue`), keep their exact snapped start time, and act as reserved layout barriers during `--sequential` planning.
If an entry contains `Attended: no`, it is marked as `SKIP` and not logged.

### 11. How are timesheet descriptions cleaned?
`analyze` produces timesheet-ready descriptions by default (F6):
- Strips ticket prefix (e.g. `PROJ-12: `) and status suffixes (`— fixed`, `- done`).
- Filters out noise lines such as file lists (`Files:`), source code paths (`src/...`), backticked tool runs (`` `pytest` ``), and `Internal notes:`.
- Trims bullet points to single sentences of up to 160 characters (capped at `TEMPO_DESCRIPTION_MAX_BULLETS`, default 4).

### 12. What if my journal timestamps record when work ended?
Set `TEMPO_HEADING_TIME=end` (or pass `--heading-time end`).
The analyzer interprets heading timestamps as completion times, calculates start times backwards using the duration, and checks elapsed intervals against previous completion times, eliminating false "estimate may be inflated" warnings.

### 13. How do fixed blocks (like lunch) work?
Define recurring slots in `TEMPO_FIXED_BLOCKS`, e.g.:
`TEMPO_FIXED_BLOCKS="13:00-14:00@LUNCH-1:Lunch"`
These slots are always kept free during `--sequential` layout so no work overlaps lunch.
Adding `--with-fixed-blocks` logs the fixed block itself unless it already exists in Tempo.

### 14. Can I map keywords to tickets automatically?
Yes. You can define keyword-to-ticket mappings in `.tempo-log/ticket-map.toml` or `~/.tempo-log/ticket-map.toml`:
```toml
[mappings]
"onboarding" = "PROJ-50"
"standup" = "MEET-100"
```
When an untagged journal entry matches a keyword, the suggestion hook automatically attaches the mapped ticket.
