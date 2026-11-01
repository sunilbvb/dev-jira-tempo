# dev-jira-tempo

Python CLI (`tempo-log`) that logs worklogs to Tempo via REST API v4. Code in `src/tempo_log/`.

## Layout
- `cli.py` args + commands (largest file; read only the part you need)
- `tempo_client.py` Tempo API, `jira_client.py` issue-key/accountId lookup
- `config.py` env loading, `journal.py` local journal

## Run
- `source .venv/bin/activate && tempo-log --help`
- Env vars in `.env` (never read or print it). See `.env.example`.

## Token-saving rules
- Do not read `.venv/`, `*.egg-info/`, `__pycache__/`, `.idea/`.
- Use Grep/targeted line ranges, not full-file reads, for `cli.py`.
- Filter API output before it enters context: request a single day or
  range, and print only id, issue, hours, description (pipe through
  `jq` or a small script). Never dump raw Tempo/Jira JSON.
- Do not re-fetch data already shown this session.
- Keep replies short. Skip recaps of diffs the user can see.
- One logging batch per session; `/clear` between batches.
- Use Explore/subagents for broad searches so file dumps stay out of context.

## Worklog rules
- Round each entry UP to the next 15 min (minimum 15m).
- Max 12h logged per day; trim overlapping/inflated entries first.
- Description: short title line, then `- ` bullets with specific
  technical detail. No casual labels ("morning session", time ranges).
- Merge contiguous work on the same issue into one entry.
- Never edit or delete entries the user added manually.
- Tempo PUT cannot change an entry's issue; recreate it instead.
- Before uploading: compare the journal against the day's meeting
  notes/recaps to catch missed meetings. A recap alone does not prove
  attendance, so ask the user which meetings they attended.
- Ask before applying any style/format decision.

## Open source
Repo is public. No company names, issue keys, ids, emails, or tokens in
code, tests, docs, or this file. Keep personal specifics in local memory.
