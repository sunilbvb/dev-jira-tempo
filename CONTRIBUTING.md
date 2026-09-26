# Contributing to dev-jira-tempo (tempo-log) ⏱️

Thank you for your interest in contributing to **dev-jira-tempo**! We welcome contributions from developers of all skill levels. Whether you are fixing a bug, adding a new feature, improving documentation, or creating new integrations (Slack bots, Raycast plugins, shell completions), your help is greatly appreciated.

---

## 📑 Table of Contents

1. [How to Get Started](#-how-to-get-started)
2. [Project Architecture Overview](#-project-architecture-overview)
3. [🚀 Open-Source Roadmap & Wishlist (Help Needed!)](#-open-source-roadmap--wishlist-help-needed)
4. [🛠️ Development Setup](#️-development-setup)
5. [🧪 Running Tests & Quality Gates](#-running-tests--quality-gates)
6. [📋 Pull Request (PR) Guidelines](#-pull-request-pr-guidelines)
7. [📐 Code Style & Standards](#-code-style--standards)

---

## 🏁 How to Get Started

1. **Fork the repository** on GitHub.
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/dev-jira-tempo.git
   cd dev-jira-tempo
   ```
3. Set up the development environment as described in [Development Setup](#️-development-setup).
4. Review the [Roadmap & Wishlist](#-open-source-roadmap--wishlist-help-needed) below or open an issue to discuss your proposal before submitting large changes.

---

## 🏗️ Project Architecture Overview

`dev-jira-tempo` is intentionally designed with **zero runtime bloat** (only requires `requests>=2.31`) and clean separation of concerns:

```text
+-----------------------------------------------------------+
|  Presentation: CLI (tempo-log) | External Python Apps    |
+-----------------------------┬-----------------------------+
                              │
                              ▼
+-----------------------------------------------------------+
|  TempoService (Core Facade & Orchestration)               |
|  src/tempo_log/service.py                                 |
+----------------------┬─────────────────────┬--------------+
                       │                     │
                       ▼                     ▼
+------------------------------+  +-------------------------+
|  TempoClient (REST v4)       |  |  JiraClient (REST v3)   |
|  src/tempo_log/tempo_client  |  |  src/tempo_log/jira_    |
+------------------------------+  +-------------------------+
                       │
                       ▼
+-----------------------------------------------------------+
|  Pluggable Storage Journals (BaseJournal, FileJournal,    |
|  MemoryJournal, NullJournal) — src/tempo_log/journal.py   |
+-----------------------------------------------------------+
```

- **CLI Layer (`src/tempo_log/cli.py`):** Thin presentation layer parsing arguments (`create`, `list`, `update`, `batch`, `doctor`) and delegating execution to `TempoService`.
- **Core Engine (`src/tempo_log/service.py`):** High-level `TempoService` facade coordinating issue key resolution, Tempo worklog creation/updates, and audit logging.
- **API Clients (`src/tempo_log/tempo_client.py` & `src/tempo_log/jira_client.py`):** Lightweight, focused HTTP clients communicating with Tempo REST API v4 and Jira Cloud REST API v3.
- **Journal Storage (`src/tempo_log/journal.py`):** Pluggable audit logger supporting file-based JSONL records, in-memory lists, or no-op silencing.
- **Configuration & Exceptions (`src/tempo_log/config.py` & `exceptions.py`):** Type-safe dataclass configurations (`Settings`, `JiraConfig`) and a unified exception tree rooted at `TempoLogError`.

---

## 🚀 Open-Source Roadmap & Wishlist (Help Needed!)

We have identified high-value features and improvements that make fantastic open-source contributions. Feel free to pick any item below!

### 📦 1. Core CLI & Standalone Capabilities (Completed ✅)
- [x] **CLI Subcommands:** `create`, `list`, `update`, `batch`, and `doctor`.
- [x] **Issue Key Auto-Resolution:** Automatically resolve issue keys (`PROJ-123`) to numeric Jira issue IDs via Jira REST API.
- [x] **Author Auto-Detection:** Automatically detect Jira `accountId` for the authenticated user.
- [x] **Audit Journaling:** Local JSONL file logger (`~/.tempo-log/journal.jsonl`) recording worklog history.
- [x] **Batch JSON Submissions:** Batch process weekly or monthly timesheets from JSON files.
- [x] **Python SDK Architecture:** Decoupled `TempoService` and exported public API in `tempo_log`.

---

### 🧠 2. Workspace & Integration Roadmap Matrix

| Feature / Scenario | Status | Description & What Needs to be Done |
|---|:---:|---|
| **1. Live Stopwatch / Timer Mode** | ✅ Implemented | `tempo-log start`, `status`, `stop` with local clock state tracking in `~/.tempo-log/active_timer.json`. |
| **2. Interactive TUI Dashboard** | ✅ Implemented | Rich/ANSI terminal dashboard with live timer display, weekly hour targets, and interactive keyboard shortcuts (`tempo-log tui`). |
| **3. OS Keyring Secret Storage** | ✅ Implemented | Secure token storage in OS keyring (macOS Keychain, Linux Secret Service, Windows Vault) via `tempo-log auth` and automatic fallback. |
| **4. Shell Tab-Completion** | ✅ Implemented | Generated shell autocompletion for Bash, Zsh, and Fish with dynamic issue key completion (`tempo-log completion`). |
| **5. Git Commit Auto-Worklog** | ✅ Implemented | Git hook (`tempo-log git-hook install/run`) to parse commit messages (e.g. `PROJ-123: 1.5h - Fix login bug`) and auto-log work. |
| **6. SQLite Audit Storage** | ✅ Implemented | Relational audit storage (`SQLiteJournal` & `DualJournal`) with range queries, weekly summaries, and CSV export (`tempo-log summary`). |
| **7. Jira Server / DC Support** | ✅ Implemented | Support for Jira Server and Data Center on-premise instances with Personal Access Token (PAT) authentication and API v2/v3 fallback. |

---

### 🛠️ Completed Capabilities:

- [x] **Live Timer Command (`tempo-log start` / `stop` / `status`):**
  - Implemented `tempo-log start` recording start timestamp, issue key, and description.
  - Implemented `tempo-log stop` calculating elapsed duration, stopping timer, and logging to Tempo.
- [x] **Weekly Summary Command (`tempo-log summary` / `tui`):**
  - Added `tempo-log summary` aggregating logged hours per day and per issue key in an easy-to-read table with targets and CSV export.
- [x] **Shell Autocompletion (`tempo-log completion`):**
  - Added autocompletion generators for `bash`, `zsh`, and `fish` completing subcommands, flags, and suggesting issue keys dynamically.
- [x] **Git Commit Hook (`tempo-log git-hook`):**
  - Automatic commit message parser supporting `#time`, `(1.5h)`, and `PROJ-123: 2h` formats.
- [x] **OS Keyring (`tempo-log auth`):**
  - Credential storage using OS native keyring backends.
- [x] **Jira Server / DC (`is_server`):**
  - Bearer PAT authentication and user resolution fallback for on-premise Jira.

---

## 🛠️ Development Setup

1. **Prerequisites:** Python 3.9+ and Git.
2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install the package in editable mode with development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```
4. **Copy the example configuration:**
   ```bash
   cp .env.example .env
   # Edit .env with your test credentials (never commit .env)
   ```

---

## 🧪 Running Tests & Quality Gates

Run the test suite using `pytest`:

```bash
pytest -v
```

Run test suite with coverage report:
```bash
pytest --cov=tempo_log -v
```

All 30 unit tests mock external network requests, so they run in **~0.10s** and do not require live credentials or internet access.

---

## 📋 Pull Request (PR) Guidelines

1. **Branch Naming:**
   - Features: `feat/interactive-timer`
   - Bug fixes: `fix/worklog-date-parsing`
   - Documentation: `docs/add-slack-example`
2. **Commit Conventions:**
   Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add live timer start/stop commands`
   - `fix: handle empty description in batch submissions`
   - `test: add coverage for Jira client timeout error`
   - `docs: update USAGE.md with shell aliases`
3. **Test Coverage:**
   - Any new feature or bug fix must include corresponding unit tests in `tests/`.
   - Ensure all existing tests pass before opening a PR.

---

## 📐 Code Style & Standards

- **Python Version Compatibility:** Must remain compatible with Python 3.9 through 3.14.
- **Type Annotations:** Use Python type hints on all public classes, methods, and functions.
- **Minimal Dependencies:** Core runtime must stay lean. Avoid adding heavy third-party dependencies unless strictly necessary and discussed beforehand.
- **Privacy & Safety:** Never hardcode credentials, corporate domains, or proprietary project names. Always use generic placeholders (`PROJ-123`, `yourcompany.atlassian.net`).
