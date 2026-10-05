## What and why

## Checks
- [ ] `python -m pytest tests/ -m "not e2e and not slow and not browser"`, `ruff check .`
- [ ] Frontend changed: `npm run lint`, `npm test`
- [ ] Should reach installed copies: `APP_VERSION` raised (and `installer.iss`), with a `## X.Y.Z` section in CHANGELOG.md
