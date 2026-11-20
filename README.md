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
  contents: write         # push CHANGELOG.md and update the Release
  pull-requests: read     # let source: auto read PR titles/descriptions

jobs:
  changelog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # required — needs full git history and tags

      - uses: GudditiN/release-scribe@v1
        with:
          api_key:        ${{ secrets.AI_API_KEY }}
          update_release: 'true'
          github_token:   ${{ secrets.GITHUB_TOKEN }}

      - name: Commit changelog
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add CHANGELOG.md
          git diff --staged --quiet || git commit -m "docs: update changelog"
          git push origin HEAD:main
```

1. Add your LLM key: **Settings → Secrets and variables → Actions → New repository secret** → name it `AI_API_KEY`.
2. Push a tag (`git tag v1.0.0 && git push origin v1.0.0`) and watch the **Actions** tab.

> **Version pinning:** `@v1` follows the latest 1.x release. For fully reproducible builds pin an exact version such as `@v1.1.4`. See [Releases](https://github.com/GudditiN/release-scribe/releases).

Want a dry run first? Add `dry_run: 'true'` — it prints the notes and writes/sends nothing.

---

## Permissions and secrets

| What | Needed for | Where |
|---|---|---|
| `permissions: contents: write` | Committing `CHANGELOG.md`, creating/updating the GitHub Release | workflow |
| `permissions: pull-requests: read` | `source: auto` / `prs` reading PR titles, descriptions and labels on **private** repos. Not needed for `source: commits`. | workflow |
| `github_token: ${{ secrets.GITHUB_TOKEN }}` | PR details and `update_release` | action input (built in, nothing to create) |
| `AI_API_KEY` (or your own name) | The LLM provider | repo secret |
| `SLACK_WEBHOOK_URL` | Slack summary message | repo secret — optional |
| `SLACK_BOT_TOKEN` + channel ID | Uploading files to Slack | repo secret — optional |

Why `pull-requests: read` matters: as soon as a workflow declares `permissions:`, every permission you don't list is set to **none**. Without it, release-scribe on a private repo can't read PR descriptions and quietly falls back to commit messages.

Secrets are never printed, and the generated text is checked for credential-like content before it is written or sent.

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
| `model` | no | provider default | Override the model, e.g. `gpt-4o` or `claude-sonnet-5-5`. Defaults can change as providers retire models, so pin one if you need stable output |
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
| `slack_style` | no | `auto` | Slack layout: `auto` (modern card, falls back automatically) \| `modern` \| `classic` |
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

Release notes are finished off with parts that come straight from GitHub, so they are always accurate and
never invented: a **Pull requests** list (links and authors), a **Contributors** line with `@handles`
(GitHub shows them as profile links, bots excluded), and a clickable **Full changelog** compare link.
The Slack card also shows a release-type badge (Major / Minor / Patch / Pre-release) and how many files
and lines changed.

Before anything is written or sent, the generated text is checked for credential-like content.

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

**Message layout (`slack_style`).** The default `auto` sends a modern card — title, previous tag → new tag, commit count, one-line summary and link buttons — followed by the full notes as formatted Markdown. If your Slack workspace rejects those newer blocks, it automatically falls back to a classic coloured card with bullet lists, then to a plain layout. Use `classic` or `modern` to force one. Text from commits and PRs is escaped, so a stray `@channel` or `<!here>` in a commit message can never ping your workspace.

#### Set up the Slack webhook (summary message) — about 2 minutes

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**. Name it (e.g. *Release Scribe*) and pick your workspace.
2. In the left menu open **Incoming Webhooks** and switch **Activate Incoming Webhooks** on.
3. Click **Add New Webhook to Workspace**, choose the channel releases should be posted to, and click **Allow**.
4. Copy the **Webhook URL** (it looks like `https://hooks.slack.com/services/T…/B…/…`).
5. In GitHub: **Settings → Secrets and variables → Actions → New repository secret** → name `SLACK_WEBHOOK_URL`, paste the URL.
6. Add `slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}` to the action step.

A webhook is tied to the channel you picked. To post to another channel, add a second webhook (repeat step 3) or create a separate secret per channel. Treat the URL as a password — anyone who has it can post to that channel.

#### Set up file upload (optional) — bot token

1. In the same Slack app open **OAuth & Permissions** → **Bot Token Scopes** → **Add an OAuth Scope** → `files:write`.
2. Click **Install to Workspace** (or **Reinstall**) and approve. Copy the **Bot User OAuth Token** (starts with `xoxb-`).
3. Save it as the GitHub secret `SLACK_BOT_TOKEN`.
4. In Slack, open the target channel and run `/invite @Release Scribe` — the bot can only upload to channels it is a member of.
5. Get the **channel ID**: open the channel → click its name → **About** → the ID is at the bottom (e.g. `C0123456789`). Use the ID, not `#name`.
6. Set `slack_mode: both` (or `files`) with `slack_bot_token` and `slack_channel_id`.

**Slack troubleshooting**

| Log message | Cause and fix |
|---|---|
| `invalid_token` / `not_authed` | Wrong or revoked bot token — reinstall the app and update the secret |
| `missing_scope` | Add the `files:write` scope, then reinstall the app |
| `channel_not_found` | Used the channel name instead of its ID, or a private channel the bot can't see |
| `not_in_channel` | Run `/invite @Release Scribe` in that channel |
| `no_service` / `invalid_payload` (webhook) | The webhook was deleted or the URL is wrong — create a new one |

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
  uses: GudditiN/release-scribe@v1
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

## Customisation cookbook

```yaml
# Plain-language notes for end users, built from PR descriptions
with:
  audience: customers
  source: auto
  style: narrative

# House style from a file in your repo (.github/release-style.md)
with:
  custom_instructions_file: '.github/release-style.md'
  project_context: 'Open-source Rust HTTP client library'

# Choose the exact range
with:
  from_tag: v2.0.0
  to_ref: main
  release_version: v2.1.0-rc1

# Several providers: fall back if the first is rate-limited
with:
  provider: groq
  api_key: ${{ secrets.GROQ_KEY }}
  fallback_providers: 'openai:gpt-4o'
  provider_keys: |
    openai=${{ secrets.OPENAI_KEY }}
```

Example `.github/release-style.md`:

```markdown
- Write for non-technical customers; avoid jargon.
- Lead each bullet with the benefit, not the implementation.
- Never mention internal ticket numbers.
- Keep the whole entry under 120 words.
```

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "No commits found in range" and no files written | Checkout is shallow — set `fetch-depth: 0`. Or the previous tag equals the new tag; tag a new commit |
| `HTTP 404 … model not found` | The model was retired or your key can't access it — set `model:` to one your provider currently lists |
| `HTTP 429` | Rate limit. The action retries with back-off; for free tiers use `fallback_providers` or `max_input_tokens` |
| Notes are vague or generic | Use `source: auto` with a `github_token` so PR descriptions are included, and write descriptive PR titles |
| Notes mention PRs the repo doesn't use | Set `source: commits` |
| "Could not find GitHub Release for tag" | Create the Release first (`gh release create vX.Y.Z`) or add a step that does, then run the action |
| `CHANGELOG.md` commit fails to push | `permissions: contents: write` is missing, or branch protection blocks the bot — push to a PR branch instead |
| Slack posts nothing | See [Slack troubleshooting](#set-up-the-slack-webhook-summary-message--about-2-minutes). Slack errors only log warnings |

## Sample Output

<img width="1010" height="562" alt="image" src="https://github.com/user-attachments/assets/8a62adef-2cb7-4587-b33f-504cbb9d535b" />


---

## License

MIT © GudditiN
