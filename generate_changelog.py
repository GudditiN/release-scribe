#!/usr/bin/env python3
"""
AI Changelog Generator
Reads commits since the last git tag and writes a polished CHANGELOG.md
and GitHub Release notes using any major LLM provider.

Providers supported: Anthropic, OpenAI, Gemini, Mistral, Groq, Cohere
"""

import os
import sys
import re
import json
import ssl
import time
import textwrap
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None


# ─────────────────────────────────────────────────────────────────
# Config (read from environment — injected by action.yml)
# ─────────────────────────────────────────────────────────────────

def env(key: str, default: str = "") -> str:
    return os.environ.get(f"INPUT_{key.upper()}", os.environ.get(key, default)).strip()


PROVIDER        = env("PROVIDER", "anthropic").lower()
API_KEY         = env("API_KEY")
MODEL           = env("MODEL")
FROM_TAG        = env("FROM_TAG")
TO_REF          = env("TO_REF", "HEAD")
RELEASE_VERSION = env("RELEASE_VERSION")
CHANGELOG_FILE  = env("CHANGELOG_FILE", "CHANGELOG.md")
OUTPUT_RELEASE  = env("OUTPUT_RELEASE_NOTES", "true").lower() == "true"
MAX_COMMITS     = int(env("MAX_COMMITS", "200") or "200")
STYLE           = env("STYLE", "keepachangelog").lower()
PROJECT_CONTEXT = env("PROJECT_CONTEXT")
GITHUB_TOKEN    = env("GITHUB_TOKEN")
UPDATE_RELEASE  = env("UPDATE_RELEASE", "false").lower() == "true"
CUSTOM_INSTRUCTIONS      = env("CUSTOM_INSTRUCTIONS")
CUSTOM_INSTRUCTIONS_FILE = env("CUSTOM_INSTRUCTIONS_FILE")
SLACK_WEBHOOK_URL        = env("SLACK_WEBHOOK_URL")
FALLBACK_PROVIDERS       = env("FALLBACK_PROVIDERS")
PROVIDER_KEYS            = env("PROVIDER_KEYS")
SLACK_MODE               = env("SLACK_MODE", "auto").lower()
SLACK_BOT_TOKEN          = env("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID         = env("SLACK_CHANNEL_ID")
UPDATE_README            = env("UPDATE_README", "false").lower() == "true"
README_FILE              = env("README_FILE", "README.md")
DRY_RUN                  = env("DRY_RUN", "false").lower() == "true"
MAX_INPUT_TOKENS         = int(env("MAX_INPUT_TOKENS", "0") or "0")  # 0 = auto per provider
GITHUB_REPO     = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_REF      = os.environ.get("GITHUB_REF", "")  # refs/tags/v1.2.3


DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-5",
    "openai":    "gpt-4o",
    "gemini":    "gemini-2.0-flash",
    "mistral":   "mistral-large-latest",
    "groq":      "openai/gpt-oss-120b",
    "cohere":    "command-r-plus",
}


# ─────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────

@dataclass
class Commit:
    sha: str
    short_sha: str
    author: str
    date: str
    subject: str
    body: str
    pr_number: Optional[int] = None
    is_merge: bool = False

    @property
    def full_message(self) -> str:
        return f"{self.subject}\n{self.body}".strip()


@dataclass
class ChangelogResult:
    changelog_entry: str      # full versioned section for CHANGELOG.md
    release_notes: str        # shorter body for GitHub Release
    from_tag: str
    commit_count: int


# ─────────────────────────────────────────────────────────────────
# Git helpers
# ─────────────────────────────────────────────────────────────────

def run_git(*args) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def latest_tag() -> str:
    """Most recent tag before TO_REF, ignoring tags that point at TO_REF itself.

    On a tag push HEAD *is* the new tag, so a plain `git describe` would return
    the tag being released and the commit range would be empty.
    """
    args = ["describe", "--tags", "--abbrev=0"]
    for t in run_git("tag", "--points-at", TO_REF).splitlines():
        if t.strip():
            args.append(f"--exclude={t.strip()}")
    tag = run_git(*args, TO_REF)
    if not tag:
        # No earlier tags — use the first commit
        tag = run_git("rev-list", "--max-parents=0", TO_REF).splitlines()[0]
    return tag


def resolve_from_tag() -> str:
    return FROM_TAG if FROM_TAG else latest_tag()


def get_commits(from_ref: str, to_ref: str) -> list[Commit]:
    sep = "||COMMIT||"
    fmt = f"%H{sep}%h{sep}%an{sep}%ad{sep}%s{sep}%b{sep}END"
    log = run_git(
        "log",
        f"{from_ref}..{to_ref}",
        f"--format={fmt}",
        "--date=short",
    )
    if not log:
        return []

    commits = []
    for block in log.split("END\n"):
        block = block.strip()
        if not block:
            continue
        parts = block.split(sep)
        if len(parts) < 6:
            continue
        sha, short_sha, author, date, subject, body = parts[:6]

        # Extract PR number from merge commits or subject
        pr_number = None
        pr_match = re.search(r"#(\d+)", subject)
        if pr_match:
            pr_number = int(pr_match.group(1))

        is_merge = subject.lower().startswith("merge")

        if MAX_COMMITS > 0 and len(commits) >= MAX_COMMITS:
            break

        commits.append(Commit(
            sha=sha, short_sha=short_sha,
            author=author, date=date,
            subject=subject.strip(), body=body.strip(),
            pr_number=pr_number, is_merge=is_merge,
        ))

    return commits


def resolve_version() -> str:
    if RELEASE_VERSION:
        return RELEASE_VERSION
    # Try to extract from GITHUB_REF (refs/tags/v1.2.3)
    if GITHUB_REF.startswith("refs/tags/"):
        return GITHUB_REF.replace("refs/tags/", "")
    # Fall back to what the next tag might be based on today
    return f"v{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


# ─────────────────────────────────────────────────────────────────
# LLM providers
# ─────────────────────────────────────────────────────────────────

def http_post(url: str, headers: dict, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "release-scribe/1.0",
        **headers
    })
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode()
            last_err = RuntimeError(f"HTTP {e.code} from {url.split('?')[0]}: {msg[:400]}")
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"  ⏳ HTTP {e.code}, retrying in {wait}s…")
                time.sleep(wait)
                continue
            raise last_err from e
        except urllib.error.URLError as e:
            last_err = RuntimeError(f"Network error calling {url.split('?')[0]}: {e}")
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise last_err from e
    raise last_err


def call_anthropic(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    data = http_post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
        {"model": model, "max_tokens": max_tokens,
         "system": system, "messages": [{"role": "user", "content": user}]}
    )
    return data["content"][0]["text"]


def call_openai(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    data = http_post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEY}"},
        {"model": model, "max_tokens": max_tokens,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]}
    )
    return data["choices"][0]["message"]["content"]


def call_gemini(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    data = http_post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}",
        {},
        {"contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
         "generationConfig": {"maxOutputTokens": max_tokens}}
    )
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_mistral(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    data = http_post(
        "https://api.mistral.ai/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEY}"},
        {"model": model, "max_tokens": max_tokens,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]}
    )
    return data["choices"][0]["message"]["content"]


def call_groq(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    data = http_post(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEY}"},
        {"model": model, "max_tokens": max_tokens,
         # gpt-oss models reason before answering; keep it short so the
         # reasoning doesn't consume the output-token budget.
         **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]}
    )
    return data["choices"][0]["message"]["content"]


def call_cohere(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    data = http_post(
        "https://api.cohere.ai/v1/chat",
        {"Authorization": f"Bearer {API_KEY}"},
        {"model": model, "max_tokens": max_tokens,
         "preamble": system, "message": user}
    )
    return data["text"]


CALLERS = {
    "anthropic": call_anthropic,
    "openai":    call_openai,
    "gemini":    call_gemini,
    "mistral":   call_mistral,
    "groq":      call_groq,
    "cohere":    call_cohere,
}


def parse_provider_keys(raw: str) -> dict:
    """Lines or comma-separated `provider=key` pairs."""
    keys = {}
    for part in re.split(r"[\n,]+", raw or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                keys[k.strip().lower()] = v.strip()
    return keys


def build_chain() -> list[tuple[str, str, str]]:
    """[(provider, model, api_key)] — primary first, then fallbacks."""
    chain = [(PROVIDER, MODEL or DEFAULT_MODELS.get(PROVIDER, ""), API_KEY)]
    keys = parse_provider_keys(PROVIDER_KEYS)
    for item in re.split(r"[\n,]+", FALLBACK_PROVIDERS):
        item = item.strip()
        if not item:
            continue
        prov, _, model = item.partition(":")
        prov = prov.strip().lower()
        if prov not in CALLERS:
            print(f"  ⚠️  Unknown fallback provider '{prov}' (ignored).")
            continue
        key = keys.get(prov) or os.environ.get(f"{prov.upper()}_API_KEY", "") \
            or (API_KEY if prov == PROVIDER else "")
        if not key:
            print(f"  ⚠️  No API key for fallback '{prov}' — add it to provider_keys (ignored).")
            continue
        chain.append((prov, model.strip() or DEFAULT_MODELS[prov], key))
    return chain


def call_llm(system: str, user: str, max_tokens: int = 4096) -> str:
    global API_KEY
    if PROVIDER not in CALLERS:
        raise ValueError(f"Unknown provider '{PROVIDER}'. Choose: {', '.join(CALLERS)}")
    chain = build_chain()
    saved_key, last = API_KEY, None
    try:
        for i, (prov, model, key) in enumerate(chain):
            API_KEY = key
            print(f"  Using {prov} / {model}" + ("  (fallback)" if i else ""))
            try:
                return CALLERS[prov](system, user, model, max_tokens)
            except Exception as e:
                last = e
                print(f"  ⚠️  {prov} failed: {str(e)[:200]}")
        raise last
    finally:
        API_KEY = saved_key


# ─────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────

STYLE_INSTRUCTIONS = {
    "keepachangelog": textwrap.dedent("""
        Format the changelog using the Keep a Changelog convention (https://keepachangelog.com).
        Group changes under these headings (omit empty sections):
          ### Added       — new features
          ### Changed     — changes to existing functionality
          ### Deprecated  — soon-to-be-removed features
          ### Removed     — now-removed features
          ### Fixed       — bug fixes
          ### Security    — security patches
        Each item is a single bullet: `- Brief description of change`
        Do not include commit SHAs or author names in the items.
    """).strip(),

    "conventional": textwrap.dedent("""
        Format the changelog using Conventional Commits grouping.
        Group changes under these headings (omit empty sections):
          ### Features (feat)
          ### Bug Fixes (fix)
          ### Performance (perf)
          ### Refactoring (refactor)
          ### Documentation (docs)
          ### Chores (chore/build/ci)
          ### Breaking Changes
        Each item is a single bullet: `- Brief description`
        Highlight breaking changes with **BREAKING:** prefix.
    """).strip(),

    "narrative": textwrap.dedent("""
        Write a narrative-style changelog in flowing prose, not bullet lists.
        Use 2-4 short paragraphs. Start with the most impactful changes.
        Be concise and friendly — write for developers reading release notes.
        You may use bold to highlight key feature names.
    """).strip(),
}


SYSTEM_PROMPT = textwrap.dedent("""
    You are a senior technical writer who creates clear, accurate, developer-friendly changelogs.

    Rules:
    - Write for the humans reading this, not for search engines.
    - Be specific — mention actual feature names, APIs, or modules when clear from the commits.
    - Skip noise: merge commits, version bumps, typo fixes, and formatting-only changes
      should be omitted or collapsed into a single brief mention.
    - Infer the intent behind cryptic commit messages — "fix bug in auth" beats "fix #1234".
    - ALWAYS group similar commits into a single bullet. For example, multiple "Adaptive X screen"
      commits should become one bullet: "Added adaptive UI support across Label, Project, Task, and About screens".
    - Expand terse commit messages into meaningful descriptions that explain the user impact.
    - Aim for 5-15 bullets total — quality over quantity.
    - Always complete every bullet point fully — never truncate mid-sentence.
    - Output ONLY the markdown content requested. No preamble, no meta-commentary.
    - Never wrap output in code fences.
""").strip()


def load_custom_instructions() -> str:
    """Combine optional inline instructions and an optional instructions file."""
    parts = []
    if CUSTOM_INSTRUCTIONS_FILE:
        if os.path.isfile(CUSTOM_INSTRUCTIONS_FILE):
            with open(CUSTOM_INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                parts.append(f.read().strip())
            print(f"  Custom instructions loaded from {CUSTOM_INSTRUCTIONS_FILE}")
        else:
            print(f"  ⚠️  custom_instructions_file not found: {CUSTOM_INSTRUCTIONS_FILE} (ignored)")
    if CUSTOM_INSTRUCTIONS:
        parts.append(CUSTOM_INSTRUCTIONS)
    text = "\n\n".join(p for p in parts if p)
    return text[:8000]  # keep the system prompt bounded


def system_prompt() -> str:
    extra = load_custom_instructions()
    if not extra:
        return SYSTEM_PROMPT
    return (SYSTEM_PROMPT
            + "\n\nAdditional project-specific instructions from the maintainers "
              "(follow these unless they conflict with the output-format rules above):\n"
            + extra)


def format_commits(commits: list[Commit]) -> str:
    return "\n".join(
        f"- [{c.short_sha}] {c.subject}"
        + (f"\n  PR: #{c.pr_number}" if c.pr_number else "")
        + (f"\n  Body: {c.body[:200]}" if c.body and len(c.body) > 5 else "")
        for c in commits
    )


def est_tokens(text: str) -> int:
    return len(text) // 4 + 1


# Input-token budget per call. Groq free tier is ~12K TPM across two calls;
# every other provider is treated as unlimited unless max_input_tokens is set.
PROVIDER_INPUT_BUDGET = {"groq": 4000}


def input_budget() -> int:
    if MAX_INPUT_TOKENS > 0:
        return MAX_INPUT_TOKENS
    return PROVIDER_INPUT_BUDGET.get(PROVIDER, 0)


def condense_commits(commits: list[Commit], budget: int) -> str:
    """Return the commit list, map-reducing it through the LLM if it exceeds budget."""
    full = format_commits(commits)
    if budget <= 0 or est_tokens(full) <= budget:
        return full

    print(f"  Commit list ~{est_tokens(full)} tokens > budget {budget}; summarising in chunks…")
    chunks, cur, cur_tokens = [], [], 0
    for c in commits:
        t = est_tokens(format_commits([c]))
        if cur and cur_tokens + t > budget:
            chunks.append(cur)
            cur, cur_tokens = [], 0
        cur.append(c)
        cur_tokens += t
    if cur:
        chunks.append(cur)

    summaries = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)} ({len(chunk)} commits)")
        summaries.append(call_llm(
            system_prompt(),
            "Condense these commits into at most 8 terse bullets that keep the "
            "specific feature/module names and user impact. Output bullets only.\n\n"
            + format_commits(chunk),
            max_tokens=700,
        ).strip())
        if PROVIDER == "groq" and i < len(chunks):
            time.sleep(10)  # stay under per-minute token limit
    return "\n".join(summaries)


def build_prompt(commit_list: str, commit_count: int, version: str, from_tag: str, style_instr: str) -> tuple[str, str]:
    ctx = f"\nProject context: {PROJECT_CONTEXT}" if PROJECT_CONTEXT else ""

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    changelog_prompt = textwrap.dedent(f"""
        Generate a CHANGELOG.md entry for version {version} (released {today}).
        Commit range: {from_tag}..HEAD  ({commit_count} commits){ctx}

        Style instructions:
        {style_instr}

        Important:
        - Group related commits into single meaningful bullets (e.g. multiple screen/UI commits → one bullet).
        - Expand terse commit messages to explain what changed and why it matters.
        - Aim for 5-15 total bullets. Skip trivial changes entirely.
        - Every bullet must be a complete sentence — never cut off mid-word or mid-sentence.

        The entry must begin with exactly:
        ## [{version}] - {today}

        Then the grouped changes below it.

        Commits to analyse:
        {commit_list}
    """).strip()

    release_prompt = textwrap.dedent(f"""
        Generate a GitHub Release body (the "What's changed" section) for version {version}.
        This will be shown on the GitHub Releases page, so keep it concise and punchy.{ctx}

        Rules:
        - Start with a 1-2 sentence summary of what this release is about.
        - Then bullet-list the top 8 most impactful changes — group similar commits into one bullet.
        - Each bullet must be a complete sentence explaining user impact, not just a commit title.
        - End with: **Full changelog**: `{from_tag}...{version}`
        - Do NOT repeat the version heading — GitHub adds it automatically.
        - Never truncate — always finish every sentence completely.
        - Use markdown but keep it clean.

        Style: {STYLE}

        Commits to analyse:
        {commit_list}
    """).strip()

    return changelog_prompt, release_prompt


# ─────────────────────────────────────────────────────────────────
# File helpers
# ─────────────────────────────────────────────────────────────────

def prepend_changelog(path: str, new_entry: str):
    """Prepend new_entry to the changelog, preserving any existing content."""
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()

    # Remove a stale entry for this same version if re-running
    version_header_pattern = re.compile(
        r"^## \[" + re.escape(resolve_version()) + r"\].*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL
    )
    existing = version_header_pattern.sub("", existing).lstrip()

    # Build header if file is new
    if not existing:
        existing = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n"

    # Insert the new entry after the top-level heading
    lines = existing.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = i + 1
            # skip blank lines after heading
            while insert_at < len(lines) and not lines[insert_at].strip():
                insert_at += 1
            break

    lines.insert(insert_at, new_entry + "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_release_notes(release_notes: str):
    path = "RELEASE_NOTES.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(release_notes + "\n")
    print(f"  Written: {path}")


def update_readme(path: str, version: str, release_notes: str):
    """Maintain a 'Latest release' block between markers in the README (opt-in)."""
    start, end = "<!-- release-scribe:start -->", "<!-- release-scribe:end -->"
    block = f"{start}\n## Latest release: {version}\n\n{release_notes}\n{end}"
    if not os.path.exists(path):
        print(f"  ⚠️  {path} not found; skipping README update.")
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if start in text and end in text:
        text = re.sub(re.escape(start) + r".*?" + re.escape(end),
                      lambda _: block, text, flags=re.DOTALL)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Updated: {path}")


def slack_context(version: str, from_tag: str, count: int) -> dict:
    """Metadata shown alongside the notes in Slack."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = GITHUB_REPO
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return {
        "repo": repo or "this project",
        "version": version, "from_tag": from_tag, "count": count,
        "model": f"{PROVIDER} / {MODEL or DEFAULT_MODELS.get(PROVIDER, '')}",
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "release_url": f"{server}/{repo}/releases/tag/{version}" if repo else "",
        "compare_url": f"{server}/{repo}/compare/{from_tag}...{version}" if repo else "",
        "run_url": f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else "",
    }


def slack_summary(ctx: dict, release_notes: str, limit: int = 2500) -> tuple[str, list]:
    """Return (fallback_text, blocks) for a release message."""
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", release_notes)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)
    fields = [
        {"type": "mrkdwn", "text": f"*Tag*\n`{ctx['version']}`"},
        {"type": "mrkdwn", "text": f"*Since*\n`{ctx['from_tag']}`"},
        {"type": "mrkdwn", "text": f"*Commits*\n{ctx['count']}"},
        {"type": "mrkdwn", "text": f"*Written by*\n{ctx['model']}"},
    ]
    links = []
    if ctx["release_url"]: links.append(f"<{ctx['release_url']}|Release>")
    if ctx["compare_url"]: links.append(f"<{ctx['compare_url']}|Compare>")
    if ctx["run_url"]:     links.append(f"<{ctx['run_url']}|Workflow run & artifacts>")
    blocks = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": f"🚀 {ctx['repo']} {ctx['version']}"[:150]}},
        {"type": "section", "fields": fields},
        {"type": "section", "text": {"type": "mrkdwn", "text": text[:limit]}},
    ]
    if links:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "  •  ".join(links)}]})
    return f"{ctx['repo']} {ctx['version']} released", blocks


def _slack_api(method: str, token: str, *, form: dict = None, body: dict = None) -> dict:
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(body).encode()
        ctype = "application/json; charset=utf-8"
    req = urllib.request.Request(
        f"https://slack.com/api/{method}", data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": ctype,
                 "User-Agent": "release-scribe/1.0"})
    with urllib.request.urlopen(req, context=_SSL_CONTEXT, timeout=30) as resp:
        out = json.loads(resp.read())
    if not out.get("ok"):
        raise RuntimeError(f"Slack {method}: {out.get('error', out)}")
    return out


def slack_upload_files(paths: list, ctx: dict, release_notes: str, brief: bool = False):
    """Upload files to a channel with the bot token (files:write scope)."""
    uploaded = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        raw = open(path, "rb").read()
        name = os.path.basename(path)
        info = _slack_api("files.getUploadURLExternal", SLACK_BOT_TOKEN,
                          form={"filename": name, "length": str(len(raw))})
        up = urllib.request.Request(info["upload_url"], data=raw, method="POST",
                                    headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(up, context=_SSL_CONTEXT, timeout=60):
            pass
        uploaded.append({"id": info["file_id"], "title": f"{ctx['version']} — {name}"})
    if not uploaded:
        raise RuntimeError("no files to upload")
    links = [u for u in (ctx["release_url"], ctx["compare_url"], ctx["run_url"]) if u]
    if brief:  # the summary message already carries the details and links
        initial = f"📎 Release files for *{ctx['repo']} {ctx['version']}*"
        links = []
    else:
        initial = (f"🚀 *{ctx['repo']} {ctx['version']}*  (since `{ctx['from_tag']}`, "
                   f"{ctx['count']} commits, {ctx['model']})\n"
                   + ("\n".join(links) if links else ""))
    _slack_api("files.completeUploadExternal", SLACK_BOT_TOKEN, body={
        "files": uploaded, "channel_id": SLACK_CHANNEL_ID, "initial_comment": initial})
    print(f"  Uploaded {len(uploaded)} file(s) to Slack channel {SLACK_CHANNEL_ID}.")


def resolve_slack_mode() -> str:
    """message | files | both | none  (from slack_mode + what is configured)."""
    mode = SLACK_MODE or "auto"
    has_msg = bool(SLACK_WEBHOOK_URL)
    has_files = bool(SLACK_BOT_TOKEN and SLACK_CHANNEL_ID)
    if mode not in ("auto", "message", "files", "both"):
        print(f"  ⚠️  Unknown slack_mode '{mode}' (use message | files | both); using auto.")
        mode = "auto"
    if mode == "auto":
        mode = "both" if (has_msg and has_files) else "message" if has_msg else "files" if has_files else "none"
    if mode in ("message", "both") and not has_msg:
        print("  ⚠️  slack_mode needs slack_webhook_url for the summary message — skipping it.")
        mode = "files" if mode == "both" and has_files else "none"
    if mode in ("files", "both") and not has_files:
        print("  ⚠️  slack_mode needs slack_bot_token AND slack_channel_id for file upload — skipping it.")
        mode = "message" if mode == "both" and has_msg else "none"
    return mode


def send_slack(version: str, from_tag: str, count: int, release_notes: str, files: list):
    """Notify Slack according to slack_mode. Never fails the release.

    message: summary post via incoming webhook (tag, details, links).
    files:   upload CHANGELOG.md / RELEASE_NOTES.md via bot token.
    both:    summary message plus the files.
    """
    mode = resolve_slack_mode()
    if mode == "none":
        return
    ctx = slack_context(version, from_tag, count)
    if mode in ("message", "both"):
        text, blocks = slack_summary(ctx, release_notes)
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL, data=json.dumps({"text": text, "blocks": blocks}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "release-scribe/1.0"})
        try:
            with urllib.request.urlopen(req, context=_SSL_CONTEXT, timeout=20):
                print("  Slack summary message sent.")
        except Exception as e:
            print(f"  ⚠️  Slack summary message failed: {e}")
    if mode in ("files", "both"):
        try:
            slack_upload_files(files, ctx, release_notes, brief=(mode == "both"))
        except Exception as e:
            print(f"  ⚠️  Slack file upload failed: {e}")


def write_release_data(version: str, from_tag: str, count: int, entry: str, notes: str):
    data = {"version": version, "from_tag": from_tag, "commit_count": count,
            "provider": PROVIDER, "model": MODEL or DEFAULT_MODELS.get(PROVIDER, ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "changelog_entry": entry, "release_notes": notes}
    with open("release-data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("  Written: release-data.json")


# ─────────────────────────────────────────────────────────────────
# GitHub Release API
# ─────────────────────────────────────────────────────────────────

def update_github_release(version: str, release_notes: str):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("  Skipping GitHub Release update (no token or repo).")
        return

    # Find the release by tag
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{version}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-changelog-generator/1.0",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            release = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  Could not find GitHub Release for tag {version}: {e.code}")
        return

    # Patch the body
    patch_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/{release['id']}"
    patch_data = json.dumps({"body": release_notes}).encode()
    patch_req = urllib.request.Request(
        patch_url, data=patch_data, method="PATCH",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-changelog-generator/1.0",
        }
    )
    with urllib.request.urlopen(patch_req) as resp:
        print(f"  GitHub Release body updated: {release['html_url']}")


# ─────────────────────────────────────────────────────────────────
# GitHub Actions output helpers
# ─────────────────────────────────────────────────────────────────

def set_output(name: str, value: str):
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            # Multi-line values use heredoc syntax
            delimiter = "EOF_DELIMITER"
            f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"::set-output name={name}::{value[:120]}…")


def set_summary(text: str):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    # Validate
    if not API_KEY:
        print("❌  AI_API_KEY (or INPUT_API_KEY) is required.")
        sys.exit(1)

    print("=" * 60)
    print("  AI Changelog Generator")
    print("=" * 60)

    # Resolve git range
    from_tag = resolve_from_tag()
    version  = resolve_version()
    print(f"  Range   : {from_tag}..{TO_REF}")
    print(f"  Version : {version}")
    print(f"  Style   : {STYLE}")
    print(f"  Provider: {PROVIDER}")

    # Fetch commits
    commits = get_commits(from_tag, TO_REF)
    if not commits:
        print("⚠️  No commits found in range. Nothing to do.")
        sys.exit(0)

    # Filter noisy commits
    noise = re.compile(
        r"^(merge (pull request|branch)|bump version|update changelog|"
        r"chore\(release\)|ci:|build\(deps\):|wip\b)",
        re.IGNORECASE
    )
    meaningful = [c for c in commits if not noise.match(c.subject) and not c.is_merge]
    print(f"  Commits : {len(commits)} total, {len(meaningful)} meaningful")

    if not meaningful:
        print("⚠️  All commits were filtered as noise. Using all commits instead.")
        meaningful = commits

    # Build prompts. Oversized histories are condensed in chunks (no hard commit cap).
    style_instr = STYLE_INSTRUCTIONS.get(STYLE, STYLE_INSTRUCTIONS["keepachangelog"])
    sys_prompt = system_prompt()
    commit_list = condense_commits(meaningful, input_budget())
    changelog_prompt, release_prompt = build_prompt(
        commit_list, len(meaningful), version, from_tag, style_instr)

    # Generate changelog entry
    print("\n📝  Generating CHANGELOG.md entry…")
    changelog_entry = call_llm(sys_prompt, changelog_prompt, max_tokens=4096).strip()

    # Generate release notes
    print("📢  Generating Release Notes…")
    if PROVIDER == "groq":
        time.sleep(10)  # stay under the free-tier per-minute token limit
    release_notes = call_llm(sys_prompt, release_prompt, max_tokens=2048).strip()

    if DRY_RUN:
        print("\n🧪  Dry run — no files written, nothing sent.\n")
        print(changelog_entry)
        print("\n--- Release notes ---\n")
        print(release_notes)
        set_output("changelog_entry", changelog_entry)
        set_output("release_notes", release_notes)
        set_output("from_tag", from_tag)
        set_output("commit_count", str(len(meaningful)))
        return

    # Write CHANGELOG.md
    print(f"\n💾  Writing {CHANGELOG_FILE}…")
    prepend_changelog(CHANGELOG_FILE, changelog_entry)
    print(f"  Written: {CHANGELOG_FILE}")

    # Write RELEASE_NOTES.md
    if OUTPUT_RELEASE:
        write_release_notes(release_notes)
    write_release_data(version, from_tag, len(meaningful), changelog_entry, release_notes)

    # Optional integrations — each only runs when configured
    if UPDATE_README:
        update_readme(README_FILE, version, release_notes)

    # Update GitHub Release body
    if UPDATE_RELEASE:
        print("🔗  Updating GitHub Release…")
        update_github_release(version, release_notes)

    if SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN:
        print("💬  Sending Slack notification…")
        files = [f for f in (CHANGELOG_FILE, "RELEASE_NOTES.md") if os.path.isfile(f)]
        send_slack(version, from_tag, len(meaningful), release_notes, files)

    # Set outputs
    set_output("changelog_entry", changelog_entry)
    set_output("release_notes", release_notes)
    set_output("from_tag", from_tag)
    set_output("commit_count", str(len(meaningful)))

    # Step summary
    set_summary(f"""### AI Changelog Generator

| | |
|---|---|
| **Version** | `{version}` |
| **Range** | `{from_tag}` → `{TO_REF}` |
| **Commits** | {len(meaningful)} |
| **Provider** | {PROVIDER} |
| **Style** | {STYLE} |

#### Preview — Release Notes

{release_notes[:800]}{'…' if len(release_notes) > 800 else ''}
""")

    print("\n✅  Done!")
    print("=" * 60)
    print(changelog_entry[:600])
    print("=" * 60)


if __name__ == "__main__":
    main()
