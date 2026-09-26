"""Git commit hook integration for automatically logging work from commit messages."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import ValidationError

logger = logging.getLogger(__name__)

# Common regex patterns for Jira issues: e.g. PROJ-123, ABC_DEF-456
ISSUE_REGEX = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")

# Duration regexes
# #time 1h 30m, #time 2h, #time 45m, #time 1.5h
TIME_TAG_REGEX = re.compile(
    r"#time\s+(?:(\d+(?:\.\d+)?)\s*h(?:ours?)?)?\s*(?:(\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?)?",
    re.IGNORECASE,
)

# (1.5h), (2h), (45m), (1h 30m)
PAREN_TIME_REGEX = re.compile(
    r"\((?:(\d+(?:\.\d+)?)\s*h(?:ours?)?)?\s*(?:(\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?)?\)",
    re.IGNORECASE,
)

# Colon duration: PROJ-123: 1.5h - Description or PROJ-123 1.5h: Description
INLINE_TIME_REGEX = re.compile(
    r"(?::\s*|\s+)(\d+(?:\.\d+)?)\s*h(?:ours?)?(?:\s+(\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?)?\s*[-:]?\s*",
    re.IGNORECASE,
)


@dataclass
class WorklogCommitInfo:
    issue_key: str
    hours: float
    description: str
    raw_message: str


def parse_duration_parts(hours_str: str | None, minutes_str: str | None) -> float | None:
    """Convert parsed hours and minutes substrings into decimal hours."""
    if not hours_str and not minutes_str:
        return None
    total = 0.0
    if hours_str:
        total += float(hours_str)
    if minutes_str:
        total += float(minutes_str) / 60.0
    return round(total, 2)


def parse_commit_message(msg: str) -> WorklogCommitInfo | None:
    """Parse commit message and extract Jira issue key, work duration, and description."""
    if not msg or not msg.strip():
        return None

    cleaned_msg = msg.strip()
    issue_match = ISSUE_REGEX.search(cleaned_msg)
    if not issue_match:
        return None

    issue_key = issue_match.group(1)
    hours: float | None = None
    desc_start = cleaned_msg

    # 1. Try '#time 1h 30m' pattern
    time_tag_match = TIME_TAG_REGEX.search(cleaned_msg)
    if time_tag_match:
        hours = parse_duration_parts(time_tag_match.group(1), time_tag_match.group(2))
        desc = TIME_TAG_REGEX.sub("", cleaned_msg).strip()
    else:
        # 2. Try '(1.5h)' paren pattern
        paren_match = PAREN_TIME_REGEX.search(cleaned_msg)
        if paren_match:
            hours = parse_duration_parts(paren_match.group(1), paren_match.group(2))
            desc = PAREN_TIME_REGEX.sub("", cleaned_msg).strip()
        else:
            # 3. Try inline: 'PROJ-123: 1.5h - description'
            # Look right after issue match
            after_issue = cleaned_msg[issue_match.end():]
            inline_match = INLINE_TIME_REGEX.match(after_issue)
            if inline_match:
                hours = parse_duration_parts(inline_match.group(1), inline_match.group(2))
                desc = after_issue[inline_match.end():].strip()
            else:
                return None

    if hours is None or hours <= 0:
        return None

    # Clean description: strip trailing/leading punctuation
    clean_desc = desc.lstrip(":- ").strip()
    # If description became empty, use the first line of the original commit message
    if not clean_desc:
        clean_desc = cleaned_msg.splitlines()[0].strip()

    return WorklogCommitInfo(
        issue_key=issue_key,
        hours=hours,
        description=clean_desc,
        raw_message=cleaned_msg,
    )


def get_latest_commit_message(repo_path: Path | str = ".") -> str:
    """Retrieve the latest commit message from git log."""
    res = subprocess.run(
        ["git", "-C", str(repo_path), "log", "-1", "--pretty=%B"],
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def install_hook(
    repo_path: Path | str = ".", hook_name: str = "post-commit"
) -> Path:
    """Install git hook into the target repository."""
    git_dir = Path(repo_path) / ".git"
    if not git_dir.exists():
        raise ValidationError(f"'{repo_path}' is not a valid git repository (missing .git).")

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / hook_name

    script_content = (
        "#!/bin/sh\n"
        "# dev-jira-tempo auto-worklog hook\n"
        "# Automatically logs work to Tempo when commit message contains issue & duration\n"
        "if command -v tempo-log >/dev/null 2>&1; then\n"
        "  tempo-log git-hook run\n"
        "elif [ -f \"./.venv/bin/tempo-log\" ]; then\n"
        "  ./.venv/bin/tempo-log git-hook run\n"
        "fi\n"
    )

    hook_file.write_text(script_content, encoding="utf-8")
    # Make executable
    os.chmod(hook_file, 0o755)
    return hook_file


def uninstall_hook(
    repo_path: Path | str = ".", hook_name: str = "post-commit"
) -> bool:
    """Uninstall git hook from the repository."""
    hook_file = Path(repo_path) / ".git" / "hooks" / hook_name
    if hook_file.exists():
        hook_file.unlink()
        return True
    return False


def run_git_hook(
    service: Any,
    commit_msg: str | None = None,
    repo_path: Path | str = ".",
) -> dict[str, Any] | None:
    """Extract worklog info from latest commit (or provided msg) and log it via TempoService."""
    msg = commit_msg
    if msg is None:
        try:
            msg = get_latest_commit_message(repo_path)
        except Exception as exc:
            logger.debug("Failed to get latest git commit: %s", exc)
            return None

    info = parse_commit_message(msg)
    if not info:
        logger.debug("No worklog information found in commit: %s", msg)
        return None

    logger.info(
        "Auto-logging %sh to %s: %s", info.hours, info.issue_key, info.description
    )
    result = service.log_time(
        hours=info.hours,
        issue=info.issue_key,
        description=info.description,
    )
    return {
        "issue": info.issue_key,
        "hours": info.hours,
        "description": info.description,
        "result": result,
    }
