# tempo-log Roadmap: From Journal to Timesheet

Sep 29, 2026 · @Sunil Bakale

## Summary

The goal: one command turns a day's work journal into a correct, reviewable timesheet, and a person only makes the judgment calls. Today the tool parses and checks a journal (`tempo-log analyze`), but rounding follow-ups, merging, meeting handling, description cleanup, duplicate checks and uploading are still done by hand or by an assistant, one step at a time.

**Split of work**

- **Tool (mechanical):** parse, round, merge, lay out, resolve issue IDs, detect duplicates and overlaps, clean descriptions, upload, verify.
- **Person (judgment):** was the meeting attended, which ticket fits, what to trim when the day is over the cap, what is billable.

**Target daily workflow**

```
tempo-log analyze journal.md --date today --plan      # preview: READY / NEEDS DECISION
tempo-log analyze journal.md --date today --submit    # upload only new, READY entries
```

Everything below is written to be generic: no company, project or person names, so it fits the open-source repo.

## Lessons learned

Two days of real journal-to-timesheet runs surfaced 12 recurring problems; each one cost a manual step or a correction.

| # | Problem observed | Effect | Fixed yet? |
| --- | --- | --- | --- |
| 1 | Journal formats drift: `### KEY [id:N]` sub-headings, headings without a date, `Time:` ranges vs `Time estimate:` | Entries silently dropped or time attached to the wrong entry | Yes (parser) |
| 2 | Per-entry 15-min round-up inflates many small entries (2m, 5m) far past the real window | 1h52m of work became 3h30m | Yes (F3 consolidation before rounding) |
| 3 | Same ticket split across many tiny entries | 7 entries for one ticket, 1h45m logged for 30m of work | Yes (F3 `--consolidate` contiguous & day) |
| 4 | Journal timestamps are written when work ends, not when it starts | False "estimate may be inflated" warnings, wrong start times | Yes (F7 `TEMPO_HEADING_TIME=end`) |
| 5 | Rounded entries overlap each other and fixed slots | Double-booked hours on the timesheet | Yes (F8 post-rounding checks, `--sequential`, `--reserve`) |
| 6 | Start times not on quarter hours (14:28, 14:58) | Messy timesheet | Yes (snapping) |
| 7 | Entries already logged by the person or another session | A duplicate worklog was created | Yes (F2 `LOGGED (#id)` duplicate matching) |
| 8 | Recurring fixed blocks (lunch) and meetings not in the journal | Missing entries; overlaps found late | Yes (F4 `TEMPO_FIXED_BLOCKS`, F5 meetings) |
| 9 | Meetings recorded as calendar invites or recap emails, not journal entries | A meeting was missed; an unattended one was nearly logged | Yes (F5 first-class meetings, `Attended: no`, F10 plugin) |
| 10 | Descriptions copied raw: file paths, tool names, internal notes, assistant narration | Every description rewritten by hand | Yes (F6 timesheet-ready descriptions, clean title & bullets) |
| 11 | Work with no ticket, or a ticket that already exists under another name | Manual Jira searches; a duplicate ticket nearly created | Yes (F9 `ticket-map.toml` & candidate hooks) |
| 12 | Journal keeps growing during the day | Hard to tell what is new since the last upload | Yes (F1 `--submit` uploads only new READY entries) |

## Proposed features

Ten features close the gaps above; F1–F6 make a normal day a single reviewed command.

### F1. Submit from analyze (`--submit`)

- **Problem:** analyze, export and batch are three steps, and nothing re-checks Tempo right before uploading.
- **Behaviour:** `analyze --submit` re-fetches the day's Tempo worklogs, skips duplicates (F2), prints the final plan and asks `Upload N entries? [y/N]`. `--yes` skips the prompt for scripts.
- **Safety:** roll back everything created in the run if any create fails; never upload BLOCKED entries; exit 1 if anything was skipped for a reason other than "already logged".
- **Done when:** a day with one duplicate and one blocked entry uploads only the rest, and a second run uploads nothing.

### F2. Skip what is already logged

- **Problem:** the journal grows during the day, and the person may also log entries directly.
- **Behaviour:** match each planned entry to existing worklogs by issue ID plus overlapping time (or same issue with same start). Matched entries show `LOGGED (#id)` and are not uploaded. Unmatched Tempo worklogs are listed as `in Tempo, not in journal` so nothing is double-counted.
- **Config:** `TEMPO_DUPLICATE_WINDOW_MINUTES` (default 15).
- **Done when:** re-running analyze after an upload shows every entry as LOGGED.

### F3. Consolidate same-ticket entries

- **Problem:** many micro-entries on one ticket each round up separately.
- **Behaviour:** `--consolidate` merges entries on the same issue that are contiguous (or separated only by entries on the same issue) into one entry. Minutes are summed before rounding; bullets are concatenated and de-duplicated; the title comes from the first entry.
- **Option:** `--consolidate=day` merges all entries on the same issue for the day, not only contiguous ones.
- **Done when:** seven 1–10 minute entries on one ticket become one 30m entry.

### F4. Fixed daily blocks from config

- **Problem:** recurring blocks such as lunch are not in the journal, so layouts overlap them.
- **Behaviour:** `TEMPO_FIXED_BLOCKS="14:00-15:00@LUNCH-KEY:Lunch"` (repeatable, `;`-separated). Each block is reserved in layout and optionally created as its own entry (`--with-fixed-blocks`). A block already in Tempo is never edited or duplicated.
- **Done when:** layout never places work inside the block and the block is logged exactly once.

### F5. Meetings as first-class entries

- **Problem:** meetings have no ticket in the journal and must keep their real time slot.
- **Behaviour:** headings starting with `Meeting:` (configurable prefix) are meetings: they default to `TEMPO_MEETING_ISSUE`, keep their actual start (snapped to the step) and act as reserved slots in `--sequential` layout.
- **Option:** `Attended: no` in the entry skips it with a note.
- **Done when:** work never overlaps a meeting and meetings need no manual ticket.

### F6. Timesheet-ready descriptions

- **Problem:** raw journal text contains file paths, tool names and internal notes.
- **Behaviour:** build `title + 1–4 bullets`. Title = heading without the ticket prefix or a generic status word ("fixed"). Drop lines matching configurable patterns: `Files:`, paths, backticked file names, `Internal notes`, tool runs (analyze/format/test commands). Trim each bullet to one sentence, max 160 characters.
- **Config:** `TEMPO_DESCRIPTION_DROP_PATTERNS`, `TEMPO_DESCRIPTION_MAX_BULLETS` (default 4).
- **Done when:** no uploaded description contains a file path or a tool command.

### F7. Heading-time mode

- **Problem:** some journals stamp a heading when work ends.
- **Behaviour:** `TEMPO_HEADING_TIME=start|end` (default `start`). With `end`, start = heading time minus duration, and "inflated estimate" warnings compare against the previous entry's end.
- **Done when:** an end-stamped journal produces no false inflated-estimate warnings.

### F8. Overlap check after rounding

- **Problem:** overlap checks use raw ranges; rounding creates new overlaps.
- **Behaviour:** always validate the final planned slots (after rounding, merging, layout) for overlaps, fixed blocks, midnight and the daily cap, and show the final timeline.
- **Done when:** a plan with any overlap cannot be submitted without `--allow-overlap`.

### F9. Ticket suggestions (integration)

- **Problem:** entries without a ticket need a manual search, and duplicates of existing tickets get created.
- **Behaviour:** for each ticketless entry, search the issue tracker by keywords from the title and bullets; show the top 3 candidates with status and assignee. A mapping file (`.tempo-log/ticket-map.toml`) remembers accepted choices by keyword.
- **Done when:** a known kind of work is mapped automatically on its second occurrence.

### F10. Meeting gap-check (integration)

- **Problem:** meetings live in calendars and recap emails, not in the journal.
- **Behaviour:** read the day's calendar events and meeting-recap notifications; list those missing from the journal with time and duration, and ask whether each was attended before adding it.
- **Done when:** every attended meeting of the day is in the journal before upload.

## Where each feature lives

F1–F8 belong in the core repo; F9–F10 need third-party accounts, so they ship as optional plugins behind a small interface.

| Feature | Home | Needs | Why there |
| --- | --- | --- | --- |
| F1 Submit | Core | Tempo token | Uses existing batch + rollback |
| F2 Skip logged | Core | Tempo token | Tempo list API only |
| F3 Consolidate | Core | Nothing | Pure planning logic |
| F4 Fixed blocks | Core | Config | Generic; values live in each user's `.env` |
| F5 Meetings | Core | Config | Generic heading prefix + meeting issue |
| F6 Descriptions | Core | Config | Patterns are configurable, no hard-coded names |
| F7 Heading time | Core | Config | Parser option |
| F8 Final checks | Core | Nothing | Validation of the final plan |
| F9 Ticket suggestions | Plugin | Jira access | Tracker-specific search |
| F10 Meeting gap-check | Plugin | Calendar / mail access | Provider-specific |

**Plugin interface (proposal):** a `tempo_log.plugins` entry point with two hooks, `suggest_tickets(entry) -> list[Candidate]` and `find_meetings(date) -> list[Meeting]`. The core only calls a hook when a plugin is installed, so the repo stays dependency-free and holds no personal or company data.

## Roadmap

Build in three phases; each starts only when the previous gate holds.

&#91;embedded content: roadmap · 3 phases, 3 gates\]

Phase 1 needs no new dependencies and removes most manual steps; phase 3 is optional and lives outside the core repo.

## Target daily workflow

With F1–F6 in place, a normal day takes one preview, a few answers and one confirmation.

1. Work as usual; the journal fills up during the day.
2. Run `tempo-log analyze journal.md --date today --plan`. The tool merges, rounds, lays out around fixed blocks and meetings, and skips what is already logged.
3. Answer only the NEEDS DECISION items: a ticket for untagged work, attended or not for a found meeting, what to trim if over the cap.
4. Run `tempo-log analyze journal.md --date today --submit` and confirm. The tool uploads, reads the entries back and prints the day's timeline.
5. Re-run any time later; only new entries are uploaded.

## Open questions

- [ ] Should consolidation (F3) be on by default, or opt-in per run?
- [ ] When the day is over the cap, should the tool propose a trim (shortest non-meeting entries first) or only warn?
- [ ] Should `--submit` require an interactive confirm even when run by an assistant, or accept `--yes`?
- [ ] Is a per-user ticket-map file (F9) acceptable in the home directory, outside the repo?
