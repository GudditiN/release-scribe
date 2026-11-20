# Changelog

All notable changes to this project will be documented in this file.

## [v1.1.7] - 2026-11-20

### Added
- Introduced a modern Slack release card layout with safer formatting and a new `slack_style` configuration option to force the legacy layout.

### Changed
- Updated the default behavior to use the new Slack layout with automatic fallbacks while keeping existing workflows unchanged.

### Fixed
- Fixed release‑note generation so Slack announcements correctly reference the previous release tag and no longer include unrelated change entries.

## [v1.1.6] - 2026-11-20

### Changed
- Improved the changelog generation logic and updated the GitHub Actions workflow to correctly tag releases, ensuring that version tags are created automatically during the release process.

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
