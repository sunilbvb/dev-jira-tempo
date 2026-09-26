"""Shell tab-completion generators for Bash, Zsh, and Fish."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .journal import DEFAULT_JOURNAL_PATH, DEFAULT_SQLITE_PATH, FileJournal


def get_recent_issues(limit: int = 30) -> list[str]:
    """Retrieve recent unique issue keys from SQLite audit or JSONL journal."""
    issues: set[str] = set()

    # 1. Try SQLite audit db
    if DEFAULT_SQLITE_PATH.exists():
        try:
            with sqlite3.connect(str(DEFAULT_SQLITE_PATH)) as conn:
                cursor = conn.execute(
                    "SELECT DISTINCT issue_key FROM worklogs WHERE issue_key IS NOT NULL AND issue_key != '' ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                for (key,) in cursor.fetchall():
                    if key:
                        issues.add(key)
        except Exception:
            pass

    # 2. Fall back / supplement with FileJournal
    if len(issues) < limit and DEFAULT_JOURNAL_PATH.exists():
        try:
            entries = FileJournal().get_recent_entries(limit=100)
            for entry in entries:
                key = entry.get("issueKey") or entry.get("issue")
                if key and isinstance(key, str) and not key.isdigit():
                    issues.add(key)
        except Exception:
            pass

    return sorted(issues)


BASH_TEMPLATE = """# Bash completion script for tempo-log
# Source this file or put it in /etc/bash_completion.d/tempo-log

_tempo_log_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="create list update batch doctor start stop status tui summary auth completion git-hook"
    local global_opts="--json --verbose -h --help"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands} ${global_opts}" -- "$cur") )
        return 0
    fi

    local subcmd="${words[1]}"

    case "$prev" in
        --issue|-i)
            local issues
            issues=$(tempo-log completion --list-issues 2>/dev/null)
            COMPREPLY=( $(compgen -W "${issues}" -- "$cur") )
            return 0
            ;;
        --hours|-H)
            COMPREPLY=( $(compgen -W "0.5 1.0 1.5 2.0 3.0 4.0 6.0 8.0" -- "$cur") )
            return 0
            ;;
        --shell)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
            return 0
            ;;
        --export-csv)
            _filedir
            return 0
            ;;
        --file|-f)
            _filedir
            return 0
            ;;
    esac

    case "$subcmd" in
        create)
            local opts="--hours -H --issue -i --issue-id --date -d --time -t --desc -m --account-id -a"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        list)
            local opts="--account-id -a --from -F --to -T --limit -n --offset"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        update)
            local opts="--id --hours -H --desc -m --date -d --time -t"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        start)
            local opts="--issue -i --issue-id --desc -m"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        stop)
            local opts="--discard --account-id -a"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        status)
            COMPREPLY=( $(compgen -W "${global_opts}" -- "$cur") )
            ;;
        summary)
            local opts="--from -F --to -T --issue -i --limit -n --export-csv"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        auth)
            local subauth="set-token get-token delete-token status"
            COMPREPLY=( $(compgen -W "${subauth} ${global_opts}" -- "$cur") )
            ;;
        completion)
            local opts="--shell --list-issues"
            COMPREPLY=( $(compgen -W "${opts} ${global_opts}" -- "$cur") )
            ;;
        git-hook)
            local subhook="install uninstall run check"
            COMPREPLY=( $(compgen -W "${subhook} ${global_opts}" -- "$cur") )
            ;;
        tui)
            COMPREPLY=( $(compgen -W "${global_opts}" -- "$cur") )
            ;;
        *)
            COMPREPLY=( $(compgen -W "${global_opts}" -- "$cur") )
            ;;
    esac
}

complete -F _tempo_log_completion tempo-log
"""

ZSH_TEMPLATE = """#compdef tempo-log
# Zsh completion script for tempo-log

_tempo_log() {
    local -a commands
    commands=(
        'create:Log work hours for an issue'
        'list:List logged worklogs'
        'update:Update an existing worklog'
        'batch:Bulk create worklogs from JSON/CSV file'
        'doctor:Verify configuration and credentials'
        'start:Start live stopwatch timer'
        'stop:Stop active timer and log time'
        'status:Show active stopwatch status'
        'tui:Launch interactive terminal dashboard'
        'summary:View weekly summary and audit log'
        'auth:Manage secure credentials in OS keyring'
        'completion:Generate shell autocompletion script'
        'git-hook:Install and run git commit auto-worklog hook'
    )

    _arguments -C \\
        '--json[Output response as JSON]' \\
        '--verbose[Enable debug logging]' \\
        '(-h --help)'{-h,--help}'[Show help message]' \\
        '1: :->command' \\
        '*:: :->args'

    case $state in
        command)
            _describe -t commands 'tempo-log command' commands
            ;;
        args)
            case $words[1] in
                create)
                    _arguments \\
                        '(-H --hours)'{-H,--hours}'[Duration in hours]:hours:(0.5 1.0 1.5 2.0 3.0 4.0 6.0 8.0)' \\
                        '(-i --issue)'{-i,--issue}'[Jira issue key]:issue:($(tempo-log completion --list-issues 2>/dev/null))' \\
                        '--issue-id[Numeric Jira issue ID]:issue_id:' \\
                        '(-d --date)'{-d,--date}'[Work date YYYY-MM-DD]:date:' \\
                        '(-t --time)'{-t,--time}'[Work start time HH:MM:SS]:time:' \\
                        '(-m --desc)'{-m,--desc}'[Work description]:desc:' \\
                        '(-a --account-id)'{-a,--account-id}'[Tempo account ID]:account:'
                    ;;
                start)
                    _arguments \\
                        '(-i --issue)'{-i,--issue}'[Jira issue key]:issue:($(tempo-log completion --list-issues 2>/dev/null))' \\
                        '--issue-id[Numeric Jira issue ID]:issue_id:' \\
                        '(-m --desc)'{-m,--desc}'[Timer description]:desc:'
                    ;;
                stop)
                    _arguments \\
                        '--discard[Discard timer without logging to Tempo]' \\
                        '(-a --account-id)'{-a,--account-id}'[Tempo account ID]:account:'
                    ;;
                summary)
                    _arguments \\
                        '(-F --from)'{-F,--from}'[Start date YYYY-MM-DD]:from:' \\
                        '(-T --to)'{-T,--to}'[End date YYYY-MM-DD]:to:' \\
                        '(-i --issue)'{-i,--issue}'[Filter by issue key]:issue:' \\
                        '--export-csv[Export audit entries to CSV]:file:_files'
                    ;;
                auth)
                    _arguments '1:subcommand:(set-token get-token delete-token status)'
                    ;;
                git-hook)
                    _arguments '1:subcommand:(install uninstall run check)'
                    ;;
            esac
            ;;
    esac
}

_tempo_log "$@"
"""

FISH_TEMPLATE = """# Fish completion script for tempo-log

# Subcommands
complete -c tempo-log -n "__fish_use_subcommand" -a create -d "Log work hours for an issue"
complete -c tempo-log -n "__fish_use_subcommand" -a list -d "List logged worklogs"
complete -c tempo-log -n "__fish_use_subcommand" -a update -d "Update an existing worklog"
complete -c tempo-log -n "__fish_use_subcommand" -a batch -d "Bulk create worklogs from JSON/CSV file"
complete -c tempo-log -n "__fish_use_subcommand" -a doctor -d "Verify configuration and credentials"
complete -c tempo-log -n "__fish_use_subcommand" -a start -d "Start live stopwatch timer"
complete -c tempo-log -n "__fish_use_subcommand" -a stop -d "Stop active timer and log time"
complete -c tempo-log -n "__fish_use_subcommand" -a status -d "Show active stopwatch status"
complete -c tempo-log -n "__fish_use_subcommand" -a tui -d "Launch interactive terminal dashboard"
complete -c tempo-log -n "__fish_use_subcommand" -a summary -d "View weekly summary and audit log"
complete -c tempo-log -n "__fish_use_subcommand" -a auth -d "Manage secure credentials in OS keyring"
complete -c tempo-log -n "__fish_use_subcommand" -a completion -d "Generate shell completion script"
complete -c tempo-log -n "__fish_use_subcommand" -a git-hook -d "Manage git commit auto-worklog hook"

# Global flags
complete -c tempo-log -l json -d "Output response as JSON"
complete -c tempo-log -l verbose -d "Enable debug logging"
complete -c tempo-log -s h -l help -d "Show help"

# Dynamic issue completion
complete -c tempo-log -l issue -s i -x -a "(tempo-log completion --list-issues 2>/dev/null)" -d "Jira issue key"

# Common options
complete -c tempo-log -n "__fish_seen_subcommand_from create" -l hours -s H -x -a "0.5 1.0 1.5 2.0 3.0 4.0 6.0 8.0" -d "Duration in hours"
complete -c tempo-log -n "__fish_seen_subcommand_from auth" -a "set-token get-token delete-token status"
complete -c tempo-log -n "__fish_seen_subcommand_from git-hook" -a "install uninstall run check"
"""


def generate_completion(shell: str) -> str:
    """Generate shell autocompletion script for bash, zsh, or fish."""
    shell_lower = shell.lower()
    if shell_lower == "bash":
        return BASH_TEMPLATE
    elif shell_lower == "zsh":
        return ZSH_TEMPLATE
    elif shell_lower == "fish":
        return FISH_TEMPLATE
    else:
        raise ValueError(f"Unsupported shell '{shell}'. Supported: bash, zsh, fish.")
