# Changelog

## [v1.1.5] - 2026-11-20

### Added
- Added comprehensive documentation covering release setup steps and required permissions for the Scribe GitHub Action.
- Improved the Marketplace listing guide with clearer instructions and updated screenshots.
- Updated the changelog to reflect the changes introduced in version v1.1.4.

## [v1.1.4] - 2026-11-19

### Added
- Introduced PR‑aware release notes with audience‑specific modes and a redesigned Slack message format. The new `source` option (`auto | commits | prs`) lets the action decide whether to summarize PR titles, descriptions, and labels (default `auto`) or fall back to raw commit messages, supporting squash‑merge and merge‑commit workflows while remaining backward compatible.

## [v1.1.3] - 2026-11-19

### Changed
- Updated the default model used for the Groq provider to improve performance and accuracy.

### Removed
- Removed Gemini from the release workflow, simplifying the action’s supported LLM providers.

All notable changes to this project will be documented in this file.

