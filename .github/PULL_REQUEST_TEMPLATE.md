## Target branch

- Feature / fix work → **`development`**
- Release integration → **`main`** (PR from `development` only)

## Checklist

- [ ] Branched from latest `development` (unless this is `development` → `main`)
- [ ] This PR is **not** a direct push to `main` or `development`
- [ ] CI green (unit, fuzz, claims, integration, Lean as applicable)
- [ ] No force-push to protected branches
