# Release Scribe

> Automatically generate polished `CHANGELOG.md` entries and GitHub Release notes from your commit history — using any LLM provider you already have a key for.

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Release%20Scribe-purple?logo=github)](https://github.com/marketplace/actions/release-scribe)
[![Release](https://img.shields.io/github/v/release/GudditiN/release-scribe)](https://github.com/GudditiN/release-scribe/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What it does

On every tag push (or manually), this action:

1. Reads all commits since the **last git tag**
2. Sends them to an LLM of your choice
3. Writes a well-structured **`CHANGELOG.md`** entry
4. Writes a concise **`RELEASE_NOTES.md`** for pasting into your GitHub Release
5. Optionally **patches the GitHub Release body** automatically

No templates. No regex. Just a model that understands what your commits actually mean.

---

## Quick start

Add this to `.github/workflows/changelog.yml` in your project:

```yaml
name: Generate Changelog

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  changelog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # required — needs full git history

      - uses: GudditiN/release-scribe@v1.0.3
        with:
          api_key:        ${{ secrets.AI_API_KEY }}
          update_release: 'true'
          github_token:   ${{ secrets.GITHUB_TOKEN }}

      - name: Commit changelog
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add CHANGELOG.md RELEASE_NOTES.md
          git diff --staged --quiet || git commit -m "docs: update changelog"
          git push origin HEAD:main
```

Add your API key: **Settings → Secrets → Actions → New secret** → name it `AI_API_KEY`.

---

## Supported providers

| Provider | Set `provider:` to | Default model | Get a key |
|---|---|---|---|
| **Anthropic** (Claude) | `anthropic` | `claude-opus-4-5` | [console.anthropic.com](https://console.anthropic.com) |
| **OpenAI** (GPT) | `openai` | `gpt-4o` | [platform.openai.com](https://platform.openai.com) |
| **Google** (Gemini) | `gemini` | `gemini-2.0-flash` | [aistudio.google.com](https://aistudio.google.com) |
| **Mistral** | `mistral` | `mistral-large-latest` | [console.mistral.ai](https://console.mistral.ai) |
| **Groq** | `groq` | `openai/gpt-oss-120b` | [console.groq.com](https://console.groq.com) |
| **Cohere** | `cohere` | `command-r-plus` | [dashboard.cohere.com](https://dashboard.cohere.com) |

---

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `api_key` | **yes** | — | API key for the chosen LLM provider |
| `provider` | no | `anthropic` | LLM provider name (see table above) |
| `model` | no | provider default | Override the model (e.g. `gpt-4-turbo`) |
| `style` | no | `keepachangelog` | `keepachangelog` \| `conventional` \| `narrative` |
| `from_tag` | no | latest git tag | Start of commit range |
| `to_ref` | no | `HEAD` | End of commit range |
| `release_version` | no | from `GITHUB_REF` | Version label for this entry |
| `changelog_file` | no | `CHANGELOG.md` | Path to your changelog file |
| `output_release_notes` | no | `true` | Also write `RELEASE_NOTES.md` |
| `max_commits` | no | `200` | Cap commits sent to the LLM (0 = unlimited) |
| `project_context` | no | — | One-liner about your project (improves quality) |
| `github_token` | no | — | Pass `secrets.GITHUB_TOKEN` to auto-update Release body |
| `update_release` | no | `false` | Patch the GitHub Release body with generated notes |
| `source` | no | `auto` | What notes are built from: `auto` \| `commits` \| `prs` — see [Where notes come from](#where-the-notes-come-from) |
| `audience` | no | `developers` | `developers` (technical) \| `customers` (plain language, skips internal-only changes) |
| `fallback_providers` | no | — | Backup models tried in order if the primary fails, e.g. `openai:gpt-4o, gemini` |
| `provider_keys` | no | — | Keys for fallback providers as `provider=key` lines (use secrets) |
| `custom_instructions` | no | — | Extra instructions for the AI (tone, audience, rules) |
| `custom_instructions_file` | no | — | Path to a file of extra instructions (combined with the above) |
| `max_input_tokens` | no | auto | Cap commit tokens per LLM call; bigger histories are summarised in chunks |
| `dry_run` | no | `false` | Print the notes only — no files written, nothing sent |
| `slack_mode` | no | `auto` | `message` \| `files` \| `both` — see [Slack](#slack-optional) |
| `slack_webhook_url` | no | — | Incoming webhook for the summary message |
| `slack_bot_token` | no | — | Bot token (`files:write`) for uploading the built files |
| `slack_channel_id` | no | — | Channel ID (e.g. `C0123456789`) for file uploads |
| `update_readme` | no | `false` | Keep a "Latest release" block in your README |
| `readme_file` | no | `README.md` | README path for `update_readme` |
| `upload_artifact` | no | `false` | Upload the built files as a downloadable workflow artifact |
| `artifact_name` | no | `release-notes` | Artifact name |

## Where the notes come from

Set `source` to choose what the AI reads:

| `source` | Reads | Best when | Needs |
|---|---|---|---|
| `auto` *(default, recommended)* | PR title, description and labels where a commit belongs to a PR; plain commit messages for direct pushes | Most teams — you get PR-quality notes without losing direct commits | `github_token` (without it, falls back to commits) |
| `prs` | Merged pull requests only; direct pushes are ignored | Teams where *everything* ships through PRs and you want release-note-style output | `github_token` |
| `commits` | Commit messages only | No PRs, Conventional Commits discipline, or no token available | nothing |

**Which is best?** PRs, in almost every case. A PR title and description explain *what changed and why* in
the author's own words, while commit messages are often terse ("fix bug", "wip"). `auto` gives you that
and still covers direct commits, so it is the default. Choose `commits` if your commit messages are already
well written (e.g. Conventional Commits) or you don't use PRs. Both squash-merge and merge-commit workflows
are supported.

Audience matters too: `audience: customers` rewrites the notes in plain language, drops internal-only work
(refactors, tests, CI), and publishes nothing at all if a release has no user-facing changes.

```yaml
with:
  source: auto
  audience: customers
  github_token: ${{ secrets.GITHUB_TOKEN }}
```

Before anything is written or sent, the generated text is checked for credential-like content, and release
notes end with a contributors line when more than one person contributed.

---

## Optional features

Everything below is **off by default** — add only what you need.

### Custom instructions

```yaml
with:
  custom_instructions: 'Write for end users, not developers. Use British spelling.'
  custom_instructions_file: '.github/release-style.md'   # optional file in your repo
```

### Backup models (multi-provider)

If the primary provider is rate-limited or down, the next one is tried automatically.

```yaml
with:
  provider: groq
  api_key: ${{ secrets.GROQ_KEY }}
  fallback_providers: 'openai:gpt-4o, gemini'
  provider_keys: |
    openai=${{ secrets.OPENAI_KEY }}
    gemini=${{ secrets.GEMINI_KEY }}
```

### Slack (optional)

Pick what Slack receives with `slack_mode`:

| `slack_mode` | Sends | Needs |
|---|---|---|
| `message` | Summary post: tag, previous tag, commit count, model, notes, links to Release / Compare / workflow run | `slack_webhook_url` |
| `files` | Uploads `CHANGELOG.md` and `RELEASE_NOTES.md` to the channel | `slack_bot_token` + `slack_channel_id` |
| `both` | The summary message, then the files | all three |
| `auto` *(default)* | Whatever you configured | — |

Incoming webhooks can't attach files, so file upload uses a bot token.

**Summary message only (simplest):** create an [Incoming Webhook](https://api.slack.com/messaging/webhooks), save the URL as secret `SLACK_WEBHOOK_URL`, then:

```yaml
with:
  slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}
```

**With files:** create a Slack app with the `files:write` scope, install it, **invite the bot to the channel** (`/invite @yourbot`), and use the channel **ID** (not the name):

```yaml
with:
  slack_mode: both
  slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}
  slack_bot_token:   ${{ secrets.SLACK_BOT_TOKEN }}
  slack_channel_id:  C0123456789
```

A Slack problem never fails your release — it logs a warning instead.

### README block and downloadable artifact

```yaml
with:
  update_readme: 'true'      # fills a block between <!-- release-scribe:start --> / <!-- release-scribe:end -->
  upload_artifact: 'true'    # CHANGELOG.md, RELEASE_NOTES.md, release-data.json under the run's Artifacts
```

### Try it safely

Set `dry_run: 'true'` to print the generated notes without writing files or sending anything.

---

## Outputs

| Output | Description |
|---|---|
| `changelog_entry` | Generated changelog section (markdown) |
| `release_notes` | Generated release notes (markdown) |
| `from_tag` | Resolved start tag |
| `commit_count` | Number of commits included |

---

## Changelog styles

### `keepachangelog` (default)

Follows [keepachangelog.com](https://keepachangelog.com) — groups changes into Added, Changed, Fixed, Security, etc.

```markdown
## [v2.1.0] - 2025-05-26

### Added
- Support for streaming responses in the API client
- New `--watch` flag for the CLI

### Fixed
- Resolved race condition in the auth token refresh flow
- Fixed incorrect pagination offset in list endpoints
```

### `conventional`

Groups by Conventional Commit type — feat, fix, perf, refactor, docs, chore.

```markdown
## [v2.1.0] - 2025-05-26

### Features
- Streaming response support in API client
- `--watch` flag for CLI

### Bug Fixes
- Race condition in auth token refresh
- Pagination offset in list endpoints
```

### `narrative`

Flowing prose — great for user-facing products and public releases.

```markdown
## [v2.1.0] - 2025-05-26

This release brings **streaming support** to the API client, making long-running
requests feel significantly more responsive. We also added a `--watch` flag to
the CLI for continuous mode.

On the stability front, we resolved a tricky race condition in the token refresh
flow that could cause spurious logouts under heavy load.
```

---

## Using the outputs in subsequent steps

```yaml
- name: Generate changelog
  id: cl
  uses: GudditiN/ai-changelog-generator@v1
  with:
    api_key: ${{ secrets.AI_API_KEY }}

- name: Create GitHub Release
  uses: softprops/action-gh-release@v2
  with:
    body: ${{ steps.cl.outputs.release_notes }}

- name: Print commit count
  run: echo "Summarised ${{ steps.cl.outputs.commit_count }} commits"
```

---

## Tips

**Always set `fetch-depth: 0`** on the checkout step. Without it, GitHub Actions does a shallow clone and the action can't see previous tags.

**Add `project_context`** — even a short sentence helps the model write more accurate bullet points:
```yaml
project_context: 'Open-source Rust HTTP client library'
```

**Manual runs** — trigger from Actions → workflow → Run workflow if you want to regenerate notes for an existing tag.

**Combine with softprops/action-gh-release** — generate notes, then use the `release_notes` output as the Release body while attaching build artifacts.

---

## License

MIT © GudditiN
