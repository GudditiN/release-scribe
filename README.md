# AI Changelog Generator

> Automatically generate polished `CHANGELOG.md` entries and GitHub Release notes from your commit history — using any LLM provider you already have a key for.

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-AI%20Changelog%20Generator-purple?logo=github)](https://github.com/marketplace/actions/ai-changelog-generator)
[![Release](https://img.shields.io/github/v/release/GudditiN/release-scribe)](https://github.com/GudditiN/release-scribe/releases/tag/v1.0.0)
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

      - uses: GudditiN/ai-changelog-generator@v1
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
| **Groq** | `groq` | `llama-3.3-70b-versatile` | [console.groq.com](https://console.groq.com) |
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
