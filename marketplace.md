# 1. Create a new public repo named: ai-changelog-generator
# 2. Push these 4 files to its root (no .github/workflows/ folder in this repo)
git init && git add . && git commit -m "feat: initial release"
git remote add origin git@github.com:YOUR_USERNAME/ai-changelog-generator.git
git push -u origin main

# 3. On GitHub: Releases → Draft new release
#    Tag: v1.0.0
#    ✅ Check "Publish this Action to the GitHub Marketplace"
#    → Publish release