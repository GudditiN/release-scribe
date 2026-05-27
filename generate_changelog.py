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
GITHUB_REPO     = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_REF      = os.environ.get("GITHUB_REF", "")  # refs/tags/v1.2.3


DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-5",
    "openai":    "gpt-4o",
    "gemini":    "gemini-2.0-flash",
    "mistral":   "mistral-large-latest",
    "groq":      "llama-3.3-70b-versatile",
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
    tag = run_git("describe", "--tags", "--abbrev=0")
    if not tag:
        # No tags at all — use the first commit
        tag = run_git("rev-list", "--max-parents=0", "HEAD")
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
    try:
        with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} from {url}: {msg[:400]}") from e


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


def call_llm(system: str, user: str, max_tokens: int = 4096) -> str:
    if PROVIDER not in CALLERS:
        raise ValueError(f"Unknown provider '{PROVIDER}'. Choose: {', '.join(CALLERS)}")
    model = MODEL or DEFAULT_MODELS[PROVIDER]
    print(f"  Using {PROVIDER} / {model}")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            return CALLERS[PROVIDER](system, user, model, max_tokens)
        except RuntimeError as e:
            msg = str(e)
            if "429" not in msg or attempt == max_retries - 1:
                raise
            wait = 65.0
            match = re.search(r"try again in ([\d.]+)s", msg)
            if match:
                wait = float(match.group(1)) + 5.0
            print(f"  Rate limited — waiting {wait:.0f}s before retry ({attempt + 1}/{max_retries})…")
            time.sleep(wait)
    raise RuntimeError("Max retries exceeded")


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


def build_prompt(commits: list[Commit], version: str, from_tag: str, style_instr: str) -> tuple[str, str]:
    ctx = f"\nProject context: {PROJECT_CONTEXT}" if PROJECT_CONTEXT else ""
    commit_list = "\n".join(
        f"- [{c.short_sha}] {c.subject}"
        + (f"\n  PR: #{c.pr_number}" if c.pr_number else "")
        + (f"\n  Body: {c.body[:200]}" if c.body and len(c.body) > 5 else "")
        for c in commits
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    changelog_prompt = textwrap.dedent(f"""
        Generate a CHANGELOG.md entry for version {version} (released {today}).
        Commit range: {from_tag}..HEAD  ({len(commits)} commits){ctx}

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

    # Build prompts
    style_instr = STYLE_INSTRUCTIONS.get(STYLE, STYLE_INSTRUCTIONS["keepachangelog"])
    changelog_prompt, release_prompt = build_prompt(meaningful, version, from_tag, style_instr)

    # Generate changelog entry
    print("\n📝  Generating CHANGELOG.md entry…")
    changelog_entry = call_llm(SYSTEM_PROMPT, changelog_prompt, max_tokens=4096).strip()

    # Generate release notes
    print("📢  Generating Release Notes…")
    release_notes = call_llm(SYSTEM_PROMPT, release_prompt, max_tokens=2048).strip()

    # Write CHANGELOG.md
    print(f"\n💾  Writing {CHANGELOG_FILE}…")
    prepend_changelog(CHANGELOG_FILE, changelog_entry)
    print(f"  Written: {CHANGELOG_FILE}")

    # Write RELEASE_NOTES.md
    if OUTPUT_RELEASE:
        write_release_notes(release_notes)

    # Update GitHub Release body
    if UPDATE_RELEASE:
        print("🔗  Updating GitHub Release…")
        update_github_release(version, release_notes)

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
