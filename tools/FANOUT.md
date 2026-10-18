# tools/fanout.py: one task across many room repos, resumable

Closes the "Dynamic Workflows / Managed Devins" gap from the Devin brief (2026-10-18, §5.2 #1) with $0 tooling.

## What it does
- Takes a **task prompt** (`--task` or `--task-file`, e.g. `tasks/agents-md-smoke.md`) and a **repo list**
  (`--repos a,b`, `--repos-file`, default: the 18 clone rooms from `preview-lift/PR_LINKS.md`).
  **gpchat is excluded by default** (live lift in progress); `--include-gpchat` overrides.
- Writes a **JSON ledger** (`work/fanout/<run-id>.json`, atomic writes) with per-repo
  `status`, branch, commit, compare/PR URL, agent id, error. Re-running the same command **resumes**:
  repos in `pushed / pr_open / launched / finished / noop` are skipped, `failed` ones are retried.
  `--only a,b` narrows one invocation, `--force a` redoes a finished repo, `--limit N` runs in waves.
- Modes (`--mode auto` picks `agents` if `CURSOR_API_KEY` is set, else `sync`):
  - **agents**: `POST https://api.cursor.com/v1/agents` per repo (`repos[0].url`, `autoCreatePR: true`).
    The `agentId` is a UUIDv5 of (run id, repo), so a resumed run gets `409` instead of a duplicate agent.
    `status --refresh` polls `GET /v1/agents/{id}` + `/runs/{runId}` and records each `prUrl`.
  - **sync**: deterministic template sync, no agent usage. Clone → branch from the default branch →
    copy `templates/room/*` → render `AGENTS.md` (`tools/room_agents_md.py`) → optional
    `--local-smoke` (Playwright) → commit → **plain push of a new branch** (never `--force`, never `main`).
    If the branch already exists remotely with identical content it is recorded as pushed; with different
    content the repo fails with a clear message. Prints the compare links to open as PRs; `record-pr` stores PR URLs.
- `--dry-run`: sync clones and renders and reports the diffstat, but commits and pushes nothing;
  agents prints the exact payload and calls no API. Dry runs use a separate `*.dryrun.json` ledger.
- Git auth: every git call uses `-c credential.helper=!<gh> auth git-credential` with the real `gh`
  (`$FANOUT_GH`, else `which gh`), so a stale `~/.gitconfig` helper path is bypassed without editing it.
- One failing repo never stops the wave; network ops retry 3x (transient TLS errors).

## Examples
```bash
python3 tools/fanout.py run --task-file tasks/agents-md-smoke.md --mode sync --dry-run --local-smoke
python3 tools/fanout.py run --task-file tasks/agents-md-smoke.md --mode sync --local-smoke
python3 tools/fanout.py status --ledger work/fanout/fanout-<id>.json
python3 tools/fanout.py record-pr --ledger work/fanout/fanout-<id>.json --repo cobrachat --pr-url https://github.com/jebbdykstra99/cobrachat/pull/14
CURSOR_API_KEY=... python3 tools/fanout.py run --task-file tasks/<task>.md --mode agents --limit 3   # pilot wave first
```

## Rules it keeps
PRs only (Jebb merges). No force-push, no pushes to `main`, no deploys, no rules publishes, no DNS.
The `agents` mode spends Cursor usage; pilot on 3 repos (`--limit 3`) before a full wave.
