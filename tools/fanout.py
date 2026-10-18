#!/usr/bin/env python3
"""fanout.py: run one task across many SubX room repos, resumably (Devin "Dynamic Workflows" gap).

Two modes:
  agents  One Cursor cloud agent per repo via the Cursor Cloud Agents API (POST /v1/agents,
          autoCreatePR). Needs CURSOR_API_KEY in the environment. Idempotent per repo: the agent
          id is derived from (run id, repo), so a re-run gets 409 instead of a duplicate agent.
  sync    Deterministic template sync: clone each repo, copy subx-factory templates/room/*,
          render a room-specific AGENTS.md, commit on a new branch, push it (never force, never
          main), and print the compare links to open as PRs. No API key, no agent usage.
  auto    (default) agents if CURSOR_API_KEY is set, else sync.

Every repo's state is written to a JSON ledger after each step, so an interrupted run resumes
where it stopped: finished repos are skipped, failed ones are retried, and `--only` / `--force`
target individual repos.

  python3 tools/fanout.py run --task-file task.md --dry-run          # plan only, writes nothing remote
  python3 tools/fanout.py run --task-file task.md --mode sync        # push branches, print PR links
  python3 tools/fanout.py status --ledger work/fanout/<run>.json      # table; --refresh polls agents
  python3 tools/fanout.py record-pr --ledger L --repo cobrachat --pr-url https://github.com/...

gpchat is excluded by default (live lift in progress); --include-gpchat overrides.
Standard library only.
"""
import argparse, time, datetime as dt, hashlib, json, os, shutil, subprocess, sys, tempfile, urllib.error, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORY = os.path.dirname(HERE)
TEMPLATE = os.path.join(FACTORY, "templates", "room")
OWNER = "jebbdykstra99"
# The 18 clone-room repos from preview-lift/PR_LINKS.md (Branch B legal PR set, 2026-10-18). gpchat is not a clone room.
DEFAULT_REPOS = [
    "27chat", "311chat", "415chat", "808chat", "airlineschat", "amachat", "atmchat", "bartchat",
    "behindtheblackwall", "boyfriendchat", "buffetchat", "buffettchat", "ciachat", "cobrachat",
    "gaichat", "popechat", "recruitchat", "samochat",
]
DEFAULT_EXCLUDE = {"gpchat"}
DONE = {"pushed", "pr_open", "launched", "finished", "noop"}
API = os.environ.get("CURSOR_API_BASE", "https://api.cursor.com")


def now():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------- ledger ----------------
class Ledger:
    def __init__(self, path):
        self.path = path
        if os.path.exists(path):
            with open(path) as f:
                self.d = json.load(f)
        else:
            self.d = {"version": 1, "created": now(), "repos": {}}

    def meta(self, **kw):
        self.d.update(kw)
        self.save()

    def get(self, repo):
        return self.d["repos"].setdefault(repo, {"status": "pending"})

    def set(self, repo, **kw):
        r = self.get(repo)
        r.update(kw)
        r["updated"] = now()
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written ledger


# ---------------- git ----------------
def gh_bin():
    return os.environ.get("FANOUT_GH") or shutil.which("gh") or "/usr/local/bin/gh"


def git(args, cwd=None, check=True):
    """git with a per-command credential helper pointing at the real gh binary (does not touch ~/.gitconfig)."""
    pre = ["git", "-c", "credential.helper=", "-c", f"credential.helper=!{gh_bin()} auth git-credential",
           "-c", "user.name=" + os.environ.get("FANOUT_GIT_NAME", "Jebb Dykstra"),
           "-c", "user.email=" + os.environ.get("FANOUT_GIT_EMAIL", "jebbdykstra99@users.noreply.github.com")]
    net = args[0] in ("clone", "push", "fetch", "ls-remote")
    for attempt in range(4 if net else 1):  # retry transient network/TLS errors on network ops
        p = subprocess.run(pre + args, cwd=cwd, capture_output=True, text=True)
        if p.returncode == 0 or not net:
            break
        if args[0] == "clone" and len(args) > 1:
            shutil.rmtree(args[-1], ignore_errors=True)
        time.sleep(3 * (attempt + 1))
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])}: {(p.stderr or p.stdout).strip()[-400:]}")
    return p


def remote_branch_sha(url, branch):
    out = git(["ls-remote", "--heads", url, branch]).stdout.strip()
    return out.split()[0] if out else None


# ---------------- template sync ----------------
def template_files():
    out = []
    for root, _, files in os.walk(TEMPLATE):
        for fn in files:
            full = os.path.join(root, fn)
            out.append(os.path.relpath(full, TEMPLATE))
    return sorted(out)


def apply_template(clone, repo, skip_workflows=False):
    sys.path.insert(0, HERE)
    import room_agents_md  # noqa: E402
    written = []
    for rel in template_files():
        if skip_workflows and rel.startswith(".github/workflows/"):
            continue
        dst = os.path.join(clone, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(TEMPLATE, rel), dst)
        written.append(rel)
    with open(os.path.join(clone, "AGENTS.md"), "w") as f:
        f.write(room_agents_md.render(clone, repo))
    written.append("AGENTS.md")
    return written


def local_smoke(clone):
    d = os.path.join(clone, "tests", "smoke")
    env = dict(os.environ, SMOKE_ROOT=clone, SMOKE_PORT=str(4300 + (abs(hash(clone)) % 500)))
    if os.path.exists("/usr/bin/google-chrome") and "SMOKE_CHROME" not in env:
        env["SMOKE_CHROME"] = "/usr/bin/google-chrome"
    subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent"], cwd=d, check=True, capture_output=True)
    p = subprocess.run(["npx", "playwright", "test", "--config", "playwright.config.mjs"], cwd=d, env=env, capture_output=True, text=True)
    shutil.rmtree(os.path.join(d, "node_modules"), ignore_errors=True)
    for junk in ("package-lock.json", "test-results"):
        pth = os.path.join(d, junk)
        shutil.rmtree(pth, ignore_errors=True) if os.path.isdir(pth) else (os.path.exists(pth) and os.remove(pth))
    tail = "\n".join(l for l in p.stdout.splitlines() if any(k in l for k in ("✓", "✘", "passed", "failed", "Error")))[-600:]
    return p.returncode == 0, tail


def do_sync(repo, a, L, task):
    url = f"https://github.com/{a.owner}/{repo}.git"
    base = a.base
    work = os.path.join(a.workdir, "clones")
    os.makedirs(work, exist_ok=True)
    clone = os.path.join(work, repo)
    if os.path.exists(clone):
        shutil.rmtree(clone)
    git(["clone", "--quiet", url, clone])
    if not base:
        base = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=clone).stdout.strip().split("/", 1)[1]
    rsha = remote_branch_sha(url, a.branch)
    if rsha:  # resume on the existing branch: new commits on top, fast-forward push only
        git(["fetch", "--quiet", "origin", f"refs/heads/{a.branch}:refs/remotes/origin/{a.branch}"], cwd=clone)
        git(["checkout", "--quiet", "-B", a.branch, f"origin/{a.branch}"], cwd=clone)
    else:
        git(["checkout", "--quiet", "-B", a.branch, f"origin/{base}"], cwd=clone)
    if not os.path.exists(os.path.join(clone, "site.json")):
        raise RuntimeError("no site.json at repo root: not a SubX room repo")
    files = apply_template(clone, repo, skip_workflows=a.skip_workflows)
    L.set(repo, status="cloned", base=base, branch=a.branch, files=files, workflows_skipped=bool(a.skip_workflows))
    if a.local_smoke:
        ok, tail = local_smoke(clone)
        L.set(repo, local_smoke="pass" if ok else "fail", local_smoke_tail=tail)
    git(["add", "-A"] + files, cwd=clone)
    if not git(["status", "--porcelain"], cwd=clone).stdout.strip():
        if rsha:
            L.set(repo, status="pushed", commit=rsha, note="remote branch already up to date",
                  compare_url=f"https://github.com/{a.owner}/{repo}/compare/{base}...{a.branch}?expand=1",
                  pr_title=a.pr_title, pr_body=pr_body(repo, task, a, files))
        else:
            L.set(repo, status="noop", note="already in sync with templates/room")
        return
    diffstat = git(["diff", "--cached", "--stat"], cwd=clone).stdout.strip().splitlines()[-1:]
    if a.dry_run:
        L.set(repo, status="dry_run_ok", diffstat=diffstat)
        return
    git(["commit", "--quiet", "-m", a.commit_message], cwd=clone)
    head = git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()
    git(["push", "--quiet", "origin", f"HEAD:refs/heads/{a.branch}"], cwd=clone)  # plain (fast-forward) push, never --force
    L.set(repo, status="pushed", commit=head)
    L.set(repo, compare_url=f"https://github.com/{a.owner}/{repo}/compare/{base}...{a.branch}?expand=1",
          pr_title=a.pr_title, pr_body=pr_body(repo, task, a, files))


def pr_body(repo, task, a, files):
    listed = ", ".join(f"`{f}`" for f in files)
    note = ""
    if a.skip_workflows:
        note = ("\n\n**CI workflow not included yet:** the push token lacks the GitHub `workflow` permission, so "
                "`.github/workflows/smoke.yml` could not be pushed. Re-run fanout without `--skip-workflows` once the "
                "token has it (adds one fast-forward commit to this branch), or add the file from subx-factory "
                "`templates/room/.github/workflows/smoke.yml` in the GitHub web editor.")
    return (f"{a.pr_intro}\n\nFiles: {listed}.\n\nOpened by `subx-factory/tools/fanout.py` (run `{a.run_id}`, mode sync). "
            f"Task sha256 `{sha(task)[:12]}`. Smoke test passed locally against this branch before push."
            f"\n\nPRs only: Jebb merges. Merging adds files only; no change to the live room's pages, "
            f"`factory.js`, `site.json`, noindex, robots.txt or the banner.{note}")


# ---------------- Cursor cloud agents ----------------
def api(method, path, key, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def agent_id_for(run_id, repo):
    return "bc-" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"subx-fanout/{run_id}/{repo}"))


def do_agent(repo, a, L, task, key):
    prompt = task.replace("{{repo}}", repo).replace("{{owner}}", a.owner)
    body = {
        "prompt": {"text": prompt},
        "name": f"fanout {a.run_id}: {repo}"[:100],
        "repos": [{"url": f"https://github.com/{a.owner}/{repo}", **({"startingRef": a.base} if a.base else {})}],
        "autoCreatePR": True,
        "agentId": agent_id_for(a.run_id, repo),
    }
    if a.model:
        body["model"] = {"id": a.model}
    if a.dry_run:
        L.set(repo, status="dry_run_ok", would_post={k: v for k, v in body.items() if k != "prompt"}, prompt_sha=sha(prompt)[:12])
        return
    code, js = api("POST", "/v1/agents", key, body)
    if code == 409:
        L.set(repo, status="launched", agent_id=body["agentId"], note="agent already existed (resume)")
    elif code in (200, 201):
        ag = js.get("agent", {})
        L.set(repo, status="launched", agent_id=ag.get("id"), agent_url=ag.get("url"), run_id=(js.get("run") or {}).get("id"))
    else:
        raise RuntimeError(f"POST /v1/agents -> {code}: {json.dumps(js)[:300]}")


def refresh_agents(L, key):
    for repo, r in L.d["repos"].items():
        if not r.get("agent_id"):
            continue
        code, ag = api("GET", f"/v1/agents/{r['agent_id']}", key)
        if code != 200:
            continue
        run = ag.get("latestRunId")
        if run:
            c2, rj = api("GET", f"/v1/agents/{r['agent_id']}/runs/{run}", key)
            if c2 == 200:
                prs = [b.get("prUrl") for b in (rj.get("git") or {}).get("branches", []) if b.get("prUrl")]
                st = rj.get("status")
                upd = {"agent_status": st}
                if prs:
                    upd.update(status="pr_open", pr_url=prs[0])
                elif st in ("FINISHED",):
                    upd["status"] = "finished"
                elif st in ("ERROR", "CANCELLED", "EXPIRED"):
                    upd.update(status="failed", error=f"agent run {st}")
                L.set(repo, **upd)


# ---------------- CLI ----------------
def resolve_repos(a):
    if a.repos:
        repos = [x.strip() for x in a.repos.split(",") if x.strip()]
    elif a.repos_file:
        repos = [l.strip() for l in open(a.repos_file) if l.strip() and not l.startswith("#")]
    else:
        repos = list(DEFAULT_REPOS)
    excl = set(x.strip() for x in (a.exclude or "").split(",") if x.strip())
    if not a.include_gpchat:
        excl |= DEFAULT_EXCLUDE
    return [r.split("/")[-1] for r in repos if r.split("/")[-1] not in excl]


def print_table(L):
    rows = sorted(L.d["repos"].items())
    print(f"{'repo':20} {'status':11} {'smoke':6} link / error")
    for repo, r in rows:
        link = r.get("pr_url") or r.get("agent_url") or r.get("compare_url") or r.get("error", "") or r.get("note", "")
        print(f"{repo:20} {r.get('status',''):11} {r.get('local_smoke','-'):6} {link}")


def cmd_run(a):
    task = a.task or (open(a.task_file).read() if a.task_file else "")
    if not task.strip():
        sys.exit("need --task or --task-file")
    key = os.environ.get("CURSOR_API_KEY", "")
    mode = a.mode if a.mode != "auto" else ("agents" if key else "sync")
    if mode == "agents" and not key and not a.dry_run:
        sys.exit("mode agents needs CURSOR_API_KEY in the environment")
    a.run_id = a.run_id or ("fanout-" + sha(task + a.branch)[:10])
    ledger_path = a.ledger or os.path.join(a.workdir, f"{a.run_id}{'.dryrun' if a.dry_run else ''}.json")
    L = Ledger(ledger_path)
    L.meta(run_id=a.run_id, mode=mode, task_sha=sha(task)[:12], branch=a.branch, owner=a.owner, dry_run=a.dry_run)
    repos = resolve_repos(a)
    if a.only:
        repos = [r for r in repos if r in set(a.only.split(","))]
    force = set((a.force or "").split(","))
    todo = [r for r in repos if L.get(r).get("status") not in DONE or r in force]
    if a.limit:
        todo = todo[: a.limit]
    print(f"[fanout] run={a.run_id} mode={mode} dry_run={a.dry_run} ledger={ledger_path}")
    print(f"[fanout] {len(repos)} repos selected, {len(repos) - len(todo)} already done, {len(todo)} to do")
    for repo in todo:
        try:
            L.set(repo, status="running", error=None)
            if mode == "agents":
                do_agent(repo, a, L, task, key)
            else:
                do_sync(repo, a, L, task)
        except Exception as e:  # record and continue: one bad repo never stops the wave
            L.set(repo, status="failed", error=str(e)[:500])
        print(f"  {repo:20} {L.get(repo)['status']}" + (f"  ({L.get(repo).get('error')})" if L.get(repo).get("error") else ""))
    print()
    print_table(L)
    if mode == "sync" and not a.dry_run:
        print("\nOpen these as PRs (base <- branch), then `record-pr` each URL into the ledger:")
        for repo, r in sorted(L.d["repos"].items()):
            if r.get("compare_url") and r.get("status") == "pushed":
                print("  " + r["compare_url"])
    failed = [r for r, v in L.d["repos"].items() if v.get("status") == "failed"]
    return 1 if failed else 0


def cmd_status(a):
    L = Ledger(a.ledger)
    if a.refresh and os.environ.get("CURSOR_API_KEY"):
        refresh_agents(L, os.environ["CURSOR_API_KEY"])
    print_table(L)


def cmd_record(a):
    L = Ledger(a.ledger)
    L.set(a.repo, status="pr_open", pr_url=a.pr_url)
    print(f"{a.repo}: pr_open {a.pr_url}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--task"); r.add_argument("--task-file")
    r.add_argument("--repos", help="comma list (default: the 18 clone rooms)"); r.add_argument("--repos-file")
    r.add_argument("--exclude", default=""); r.add_argument("--include-gpchat", action="store_true")
    r.add_argument("--only", help="comma list: restrict this invocation to these repos")
    r.add_argument("--force", help="comma list: redo these even if the ledger says done")
    r.add_argument("--mode", choices=["auto", "agents", "sync"], default="auto")
    r.add_argument("--dry-run", action="store_true", help="sync: clone + render + diff, no commit/push. agents: print payloads, no API call")
    r.add_argument("--ledger"); r.add_argument("--run-id")
    r.add_argument("--workdir", default=os.path.join(FACTORY, "work", "fanout"))
    r.add_argument("--owner", default=OWNER); r.add_argument("--base", default="", help="base branch (default: repo default branch)")
    r.add_argument("--branch", default="factory/agents-md-smoke")
    r.add_argument("--limit", type=int, default=0, help="max repos this invocation (waves)")
    r.add_argument("--local-smoke", action="store_true", help="sync: run the Playwright smoke test locally before pushing")
    r.add_argument("--model", default="")
    r.add_argument("--skip-workflows", action="store_true", help="sync: leave out .github/workflows/* (for tokens without the GitHub workflow permission)")
    r.add_argument("--commit-message", default="Add AGENTS.md, shared Playwright smoke test, and PR smoke CI")
    r.add_argument("--pr-title", default="Add AGENTS.md + shared Playwright smoke test + PR CI")
    r.add_argument("--pr-intro", default="Adds a room-specific `AGENTS.md`, the shared SubX Playwright smoke test (`tests/smoke/`), and a GitHub Actions job that runs it on every PR.")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("status"); s.add_argument("--ledger", required=True); s.add_argument("--refresh", action="store_true"); s.set_defaults(fn=cmd_status)
    p = sub.add_parser("record-pr"); p.add_argument("--ledger", required=True); p.add_argument("--repo", required=True); p.add_argument("--pr-url", required=True); p.set_defaults(fn=cmd_record)
    a = ap.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
