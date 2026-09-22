#!/usr/bin/env python3
"""rpilayer: state helper for HumanLayer's RPI skills, without the HumanLayer app.

  rpilayer.py base                 RPI plugin dir in the local HumanLayer checkout
  rpilayer.py state [SLUG]         task state + deterministic next step (JSON)
  rpilayer.py migrate [SLUG]       import legacy tasks without overwriting conflicts
  rpilayer.py judge SLUG           ask Jev what the user's message means; reads
                                   {"message", "conversation": [{"role", "text"}]} on stdin
  rpilayer.py view ARTIFACT.md     wrap the HTML body read from stdin in the view
                                   template, write ARTIFACT.html next to it
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

REPO_URL = "https://github.com/humanlayer/humanlayer.git"
PLUGIN = "apps/riptide-rpi-claude-plugin"
# The daemon defines the rpi:* subagents in TypeScript; the plugin ships no agents/ dir.
AGENTS = "apps/riptide-daemon/src/agents/claudecode/agents"
REFRESH_SECONDS = 24 * 3600
# Longest first so "research-questions" wins over "research".
KINDS = ["research-questions", "research", "design-discussion", "structure-outline", "plan", "prd", "tdd"]
ARTIFACT = re.compile(r"^(\d{2})-(" + "|".join(KINDS) + r")-.+\.md$")

NEXT = {
    None: "create-research-questions",
    "research-questions": "create-research",
    "research": "create-design-discussion",
    "prd": "create-tdd",
    "tdd": "create-structure-outline",
}
ITERATE = {
    "research-questions": "iterate-research-questions",
    "research": "iterate-research",
    "design-discussion": "iterate-design-discussion",
    "prd": "iterate-prd",
    "tdd": "iterate-tdd",
    "structure-outline": "iterate-structure-outline",
    "plan": "iterate-plan",
}


def humanlayer():
    """Sparse, shallow checkout of HumanLayer's repo, refreshed at most once a day."""
    if os.environ.get("RPI_REPO"):
        return Path(os.environ["RPI_REPO"])
    repo = Path.home() / ".rpilayer/humanlayer"
    stamp = repo / ".git/rpilayer-fetched"
    run = lambda *a, timeout=60: subprocess.run(["git", *a], capture_output=True, text=True, timeout=timeout, check=True)
    try:
        if not (repo / ".git").is_dir():
            run("clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO_URL, str(repo), timeout=300)
            run("-C", str(repo), "sparse-checkout", "set", PLUGIN, AGENTS)
            stamp.touch()
        elif not stamp.exists() or time.time() - stamp.stat().st_mtime > REFRESH_SECONDS:
            run("-C", str(repo), "fetch", "--depth", "1", "origin", "HEAD")
            # It is a cache nobody edits, so hard reset is safe.
            run("-C", str(repo), "reset", "--hard", "FETCH_HEAD")
            stamp.touch()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        if not (repo / PLUGIN).is_dir():
            raise RuntimeError(f"cannot fetch {REPO_URL} into {repo}: {getattr(error, 'stderr', '') or error}")
        # ponytail: offline keeps the last copy and retries on the next call.
    return repo


def base():
    return humanlayer() / PLUGIN


def agents():
    return humanlayer() / AGENTS


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def repo_root():
    # The common git dir points at the main checkout even from inside a worktree,
    # so tasks stay in one place for every worktree of the repo.
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        sys.exit("not inside a git repository")
    return Path(common).parent


def tasks_root():
    # Local Git config is shared by worktrees and survives moving the checkout.
    repo_id = git("config", "--local", "--get", "rpilayer.repo-id")
    if not repo_id:
        candidate = uuid.uuid4().hex
        result = subprocess.run(
            ["git", "config", "--local", "--replace-all", "rpilayer.repo-id", candidate, "^$"],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError("cannot persist rpilayer repository identity")
        repo_id = git("config", "--local", "--get", "rpilayer.repo-id")
    if not re.fullmatch(r"[0-9a-f]{32}", repo_id):
        raise ValueError("invalid rpilayer.repo-id in local Git config")
    return Path.home() / ".rpilayer/repos" / repo_id / "tasks"


def validate_slug(slug):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("task slug must be kebab-case")


def legacy_roots():
    listing = git("worktree", "list", "--porcelain", "-z")
    roots = {Path(field[9:]).resolve() / ".humanlayer/tasks"
             for field in listing.split("\0") if field.startswith("worktree ")}
    return sorted(roots)


def task_slugs(roots):
    return sorted({p.name for root in roots if root.is_dir()
                   for p in root.iterdir() if p.is_dir()})


def migrate(slug=None):
    tasks = tasks_root()
    roots = legacy_roots()
    if slug:
        validate_slug(slug)
    slugs = [slug] if slug else task_slugs(roots)
    sources = [root / name for root in roots for name in slugs if (root / name).is_dir()]
    pending = {}
    conflicts = []
    for source in sources:
        validate_slug(source.name)
        if source.is_symlink():
            conflicts.append({"source": str(source), "reason": "symlink requires manual migration"})
            continue
        for file in sorted(source.rglob("*")):
            if file.is_symlink():
                conflicts.append({"source": str(file), "reason": "symlink requires manual migration"})
                continue
            if not file.is_file():
                continue
            target = tasks / source.name / file.relative_to(source)
            data = file.read_bytes()
            if ((target in pending and pending[target] != data)
                    or (target.exists() and (not target.is_file() or target.read_bytes() != data))):
                conflicts.append({"source": str(file), "target": str(target), "reason": "different content"})
            else:
                pending[target] = data
    for target in pending:
        if target.is_symlink():
            conflicts.append({"target": str(target), "reason": "symlink requires manual migration"})
        parent = target.parent
        while parent != tasks.parent:
            if parent in pending or parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                conflicts.append({"target": str(target), "reason": f"unsafe parent path: {parent}"})
                break
            parent = parent.parent
    if conflicts:
        return {"error": "migration conflicts; reconcile the listed files and retry", "conflicts": conflicts}
    for target, data in pending.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as file:
                file.write(data)
        except FileExistsError:
            if target.read_bytes() != data:
                raise RuntimeError(f"migration target changed: {target}") from None
    # Keep original directories as backups, outside the legacy task discovery path.
    backups = []
    for source in sources:
        (tasks / source.name).mkdir(parents=True, exist_ok=True)
        backup = source.parent.parent / "rpilayer-migrated" / uuid.uuid4().hex / source.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        source.rename(backup)
        backups.append(str(backup))
    return {"tasks_dir": str(tasks), "migrated": slugs, "backups": backups}


def open_design_questions(text):
    m = re.search(r"^### Design Questions\s*$(.*?)(?=^### |\Z)", text, re.M | re.S)
    return len(re.findall(r"^#### ", m.group(1), re.M)) if m else 0


def checkboxes(text):
    # Outlines list "- [ ] Phase N: ..." in their overview; those decide completion, because
    # the per-phase boxes include manual device checks an agent can never tick.
    # Documents without phase lines fall back to every checkbox.
    phase = r"Phase \d+:" if re.search(r"^\s*- \[[ xX]\] Phase \d+:", text, re.M) else ""
    return (len(re.findall(r"^\s*- \[ \] " + phase, text, re.M)),
            len(re.findall(r"^\s*- \[[xX]\] " + phase, text, re.M)))


def current_phase(text):
    # The first unticked "- [ ] Phase N: title" line is the phase being implemented.
    m = re.search(r"^\s*- \[ \] (Phase \d+:.*?)\s*$", text, re.M)
    return m[1] if m else None


def next_step(latest, open_questions=0, unchecked=0, checked=0):
    if latest == "design-discussion":
        return "iterate-design-discussion" if open_questions else "create-structure-outline"
    if latest in ("structure-outline", "plan"):
        if checked and not unchecked:
            return "describe-pr"
        # No setup-worktree step: the user makes the worktree before the task starts.
        return "implement-outline" if latest == "structure-outline" else "implement-plan"
    return NEXT[latest]


# What each track writes before the outline; `steps` lays the task out against it.
TRACKS = {"research": ["research-questions", "research", "design-discussion"], "product": ["prd", "tdd"]}
LABELS = {"research-questions": "questions", "design-discussion": "design", "structure-outline": "outline",
          "describe-pr": "pr"}


def step_of(next_name):
    # The step a `next` value works on: create-research and iterate-research are both "research".
    if next_name.startswith("implement-"):
        return "implement"
    if next_name == "describe-pr":
        return next_name
    return re.sub(r"^(create|iterate)-", "", next_name)


def steps(kinds, next_name, open_questions=0, unchecked=0, checked=0, phase=None):
    """The whole workflow for display: each step done, current, skipped or todo.

    Built from the documents actually written, so a document outside the usual track shows up
    where it was written, and a step the task went past without its document shows as skipped.
    """
    kinds = list(dict.fromkeys(kinds))
    current = step_of(next_name)
    is_product = bool({"prd", "tdd"} & set(kinds)) or current in TRACKS["product"]
    names = list(TRACKS["product" if is_product else "research"])
    for prev, kind in zip([None, *kinds], kinds):
        if kind not in names and kind not in ("structure-outline", "plan"):
            names.insert(names.index(prev) + 1 if prev in names else 0 if prev is None else len(names), kind)
    outline = "plan" if "plan" in kinds and "structure-outline" not in kinds else "structure-outline"
    names += [outline, "implement", "describe-pr"]

    done = set(kinds)
    if checked and not unchecked:
        done.add("implement")
    # A current step the list does not show marks nothing as skipped.
    at = names.index(current) if current in names else -1
    out = []
    for i, name in enumerate(names):
        if name == current:
            status = "current"
        elif name in done:
            status = "done"
        elif i < at:
            status = "skipped"
        else:
            status = "todo"
        step = {"name": name, "label": LABELS.get(name, name), "status": status}
        if name == "implement" and checked + unchecked:
            # While implementing, count the phase being worked on, not the ones finished.
            step["detail"] = (f"phase {checked + 1}/{checked + unchecked}" if status == "current" and unchecked
                              else f"{checked}/{checked + unchecked}")
            if status == "current" and phase:
                step["doing"] = phase
        if name == "design-discussion" and open_questions:
            step["detail"] = f"{open_questions} open"
        out.append(step)
    return out


def worktree_link():
    # A linked worktree has its own git dir, so a file there belongs to that worktree only and
    # goes away with it. The main checkout hosts many tasks, so it never remembers one.
    own = git("rev-parse", "--path-format=absolute", "--git-dir")
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(own) / "rpilayer-slug" if own and own != common else None


def state(slug=None):
    root = repo_root()
    tasks = tasks_root()
    legacy = legacy_roots()
    slugs = task_slugs([tasks, *legacy])
    link = worktree_link()
    if not slug:
        linked = link.read_text().strip() if link and link.is_file() else ""
        branch = git("branch", "--show-current")
        # A task with a PR description is finished: never resume it just for being the only one.
        open_slugs = [s for s in slugs if not (tasks / s / "pr-description.md").exists()]
        slug = (linked if linked in slugs else branch if branch in slugs
                else open_slugs[0] if len(open_slugs) == 1 else None)
    if not slug:
        return {"repo": str(root), "tasks_dir": str(tasks), "base": str(base()), "agents": str(agents()), "tasks": slugs, "error": "pick a task slug (or create one)"}

    validate_slug(slug)
    if link:
        # Naming a task in a worktree ties it there, even when the branch has another name.
        link.write_text(slug)
    task_dir = tasks / slug
    sources = [str(path / slug) for path in legacy if (path / slug).is_dir()]
    if sources:
        return {"repo": str(root), "slug": slug, "task_dir": str(task_dir),
                "error": "legacy tasks require explicit migration before continuing",
                "migration_required": True, "legacy_task_dirs": sources}
    files = sorted(p.name for p in task_dir.iterdir() if p.is_file()) if task_dir.is_dir() else []
    artifacts = [{"nn": m[1], "kind": m[2], "file": f} for f in files if (m := ARTIFACT.match(f))]
    latest = artifacts[-1] if artifacts else None
    kind = latest["kind"] if latest is not None else None
    text = (task_dir / latest["file"]).read_text() if latest else ""
    oq = open_design_questions(text) if kind == "design-discussion" else 0
    unchecked, checked = checkboxes(text) if kind in ("structure-outline", "plan") else (0, 0)
    phase = current_phase(text) if kind in ("structure-outline", "plan") else None
    nxt = next_step(kind, oq, unchecked, checked)

    return {
        "repo": str(root),
        "slug": slug,
        "task_dir": str(task_dir),
        "base": str(base()),
        "agents": str(agents()),
        "has_ticket": any(f in files for f in ("ticket.md", "task.md")),
        "artifacts": artifacts,
        "latest": latest,
        "open_design_questions": oq,
        "checkboxes": {"unchecked": unchecked, "checked": checked},
        "next": nxt,
        "steps": steps([a["kind"] for a in artifacts], nxt, oq, unchecked, checked, phase),
        "iterate": (ITERATE.get(kind) or "iterate-implementation") if kind is not None else None,
    }


# Jev allows 32k tokens for state + question, and loses accuracy on irrelevant bulk, so
# context is capped by characters (~4 per token) and trimmed from the oldest end.
CONVERSATION_CHARS = 60_000
OPEN_SECTIONS_CHARS = 16_000


def open_sections(text):
    # Only the parts of the artifact a reply is likely to react to: open questions and decisions.
    parts = re.split(r"(?m)^(?=#{2,3} )", text)
    keep = [p for p in parts if re.match(r"#{2,3} .*(question|decision|open|risk)", p, re.I)]
    return "\n".join(keep)[:OPEN_SECTIONS_CHARS]


def recent(conversation, budget=CONVERSATION_CHARS):
    kept = []
    for turn in reversed(conversation):
        if budget <= 0:
            break
        text = turn["text"][:budget]
        kept.append({"role": turn["role"], "text": text})
        budget -= len(text)
    return kept[::-1]


def judge(slug, ctx):
    s = state(slug)
    if s.get("error"):
        return {"state": s, "error": s["error"]}
    latest = s.get("latest")
    payload = {
        "model": "jev-latest",
        "state": {
            "workflow": {
                "phase": latest["kind"] if latest else "no artifacts yet",
                "current_document": latest["file"] if latest else None,
                "next_step": s.get("next"),
                "iterate_step": s.get("iterate"),
                "open_design_questions": s.get("open_design_questions"),
                "phases": s.get("checkboxes"),
            },
            "document_open_sections": open_sections((Path(s["task_dir"]) / latest["file"]).read_text()) if latest else "",
            "conversation": recent(ctx.get("conversation", [])),
            "user_message": ctx["message"],
        },
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": "The user is working through a research-plan-implement workflow and is "
                "currently at `workflow.phase`. `user_message` is their reply to the agent's last turn in "
                "`conversation`; read it as an answer to that turn, using `document_open_sections` for what "
                "is still pending. What does `user_message` ask the agent to do?",
                "criteria": {
                    "advance": "Approves the current document, asks to move on to `workflow.next_step`, or "
                    "confirms that the agent understood an earlier request correctly, without asking for anything new",
                    "iterate": "Asks for new changes, corrections or additions to the current document that the "
                    "agent has not already made",
                    "question": "Asks a question about the document or the code, without asking for changes",
                    "other": "Something unrelated to the workflow",
                },
            },
            "product_first": {
                "type": "noul",
                "instructions": "Does `user_message` describe a product or UX problem whose desired "
                "behavior is still undefined, rather than a technical change with a known goal?",
            },
        },
    }
    req = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}", "Content-Type": "application/json"},
    )
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.HTTPSHandler())
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    with opener.open(req, timeout=30) as r:
        try:
            response = json.load(r)
        except ValueError as error:
            raise ValueError("judge API returned invalid JSON") from error
        return {"state": s, "answers": response["answers"]}


def render(template, title, content, source):
    # Plain replace, not str.format: CSS and JS are full of braces.
    return template.replace("{{TITLE}}", html.escape(title)).replace("{{SOURCE}}", html.escape(source)).replace("{{CONTENT}}", content)


def view(md, content):
    first_h1 = re.search(r"^# (.+)$", md.read_text(), re.M)
    out = md.with_suffix(".html")
    template = (Path(__file__).resolve().parent / "view-template.html").read_text()
    out.write_text(render(template, first_h1[1] if first_h1 else md.stem, content, md.name))
    return out


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["state"]
    try:
        if cmd == "base":
            print(base())
        elif cmd == "state" and len(args) <= 1:
            print(json.dumps(state(*args), indent=2))
        elif cmd == "migrate" and len(args) <= 1:
            print(json.dumps(migrate(*args), indent=2))
        elif cmd == "judge" and len(args) == 1:
            print(json.dumps(judge(args[0], json.load(sys.stdin)), indent=2))
        elif cmd == "view" and len(args) == 1:
            print(view(Path(args[0]), sys.stdin.read()))
        else:
            sys.exit(__doc__)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"error": str(error)}, indent=2))
        sys.exit(1)
