# Publishing Release Scribe to the GitHub Marketplace (maintainer checklist)

The Marketplace page is generated from `README.md`, `action.yml` (name, description, branding) and the
release you publish. Nothing is uploaded separately.

## Before each release
- [ ] README inputs table matches `action.yml` inputs
- [ ] README examples use `@v1` (or the new exact version) — no stale pins
- [ ] Provider default models in `generate_changelog.py` still exist (check each provider's model list)
- [ ] `python3 -m py_compile generate_changelog.py` and the action YAML parses

## Publish
1. Merge to `main`.
2. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`
   (this repo's own workflow then drafts the notes and posts to Slack).
3. GitHub → **Releases** → open the release for the tag → **Edit**.
4. Tick **Publish this Action to the GitHub Marketplace**.
5. Choose a **primary category** (e.g. *Utilities*) and optionally a second one.
6. **Update release**.

## Keep `@v1` current
```bash
git tag -fa v1 -m "v1"
git push origin v1 --force   # moves only the v1 tag
```

## Listing quality tips
- Keep `description` in `action.yml` under ~125 characters; it is the Marketplace tagline.
- First screen of the README is what people read: what it does, a 20-line quick start, then details.
- Add screenshots of the Slack message and a sample Release (Markdown images in the README).
- Add repository topics (Settings → About): `changelog`, `release-notes`, `github-actions`, `llm`.
