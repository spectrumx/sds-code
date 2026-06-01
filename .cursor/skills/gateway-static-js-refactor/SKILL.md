---
name: gateway-static-js-refactor
description: Plans and executes refactors of SDS gateway browser JavaScript (gateway/sds_gateway/static/js) for brevity, lower complexity, parity, and reviewability. Uses Fallow metrics, Django template/RenderHTMLFragment rendering, DRY reuse, and django_javascript_implementation rules. Use for large JS refactors, reducing duplication, moving HTML out of JS, or when the user asks for refactor scenarios or fallow checks.
---

# Gateway static JS refactor

## When to apply

- Refactors under `gateway/sds_gateway/static/js/` (especially managers/handlers in `actions/`, `core/`, `dataset/`, `search/`, `share/`, `upload/`, `visualizations/`)
- User wants **scenarios**, a **phased plan**, or **metrics before/after**
- Removing inline HTML strings, cross-file duplication, or high-complexity hotspots
- Aligning new behavior with existing classes instead of one-off helpers

**Out of scope:** `deprecated/` (never edit). For tests after refactor, use [jest-test-writing](../jest-test-writing/SKILL.md).

## Optimization goals (in order)

1. **Functionality parity** — same user-visible behavior, API contracts, and error handling intent
2. **Human reviewability** — small, ordered commits or phases; each diff explainable in one paragraph
3. **Low method complexity** — shallow nesting, early returns, single responsibility
4. **Brevity** — fewer lines only when clarity is preserved (not golf)

## Mandatory conventions

Follow `.cursor/rules/django_javascript_implementation.mdc` in full. Non-negotiables for refactors:

| Area | Rule |
|------|------|
| JS location | Logic in `.js` files under `static/js/` subfolders; templates only **initialize** classes |
| New files | Ask before new templates; ask before new `.js` files (purpose + function list) |
| New classes | Own file in a subfolder (`actions/`, `core/`, …), not base `js/` |
| HTML | Dynamic markup → `templates/.../components/*.html` + `POST /users/render-html/` via `APIClient` / `DOMUtils`; **never** build HTML fragments in JS |
| Asset types | Configuration-driven (`constants/`, config objects), not `if (type === 'capture')` sprawl |
| Reuse | Grep for existing method/class names; **extend or generalize** before adding parallel APIs |

## Workflow

Copy and track:

```text
Refactor progress:
- [ ] Baseline (fallow + identify targets)
- [ ] Propose 2–4 scenarios (user picks or hybrid)
- [ ] Implement phase 1 (smallest parity-preserving slice)
- [ ] Tests + fallow + cross-file dupes
- [ ] Implement remaining phases
- [ ] Final metrics + review notes
```

### 1. Baseline (always run from `gateway/`)

```bash
npm run fallow
npx fallow health --format human
npx fallow dupes --format human
npm run fallow:static-js
bash scripts/fallow-cross-file-dupes.sh
```

For work on a branch, scope noise:

```bash
npx fallow audit --changed-since main --format human
```

Record: worst complexity hotspots, clone groups touching your files, new dead exports.

Details: [fallow-gateway.md](fallow-gateway.md).

### 2. Discover reuse (before writing code)

- Search `static/js` for the same DOM ids, `render-html` templates, `ListRefreshManager`, `DOMUtils` helpers, and action manager patterns
- Check `constants/` (`detailsModalConfig`, `FileListConfig`, permission levels)
- Prefer widening an existing util/manager over a feature-specific function

### 3. Propose refactor scenarios

Present **2–4 options** with tradeoffs. Typical scenario types:

| Scenario | Best when | Risk |
|----------|-----------|------|
| **Extract + name** | One 200+ line method or deep nesting | Low if tests exist |
| **Consolidate duplicates** | Fallow `dupes` or copy-pasted blocks across files | Medium — watch cross-file pre-commit |
| **Config extraction** | Repeated asset-type branches | Low if config matches existing constants style |
| **Template migration** | Large `` `...html...` `` or string concatenation in JS | Medium — needs component template + view context |
| **Delegate to existing API** | Reinventing list refresh, modals, permissions | Low |
| **Split class by concern** | God-class with unrelated responsibilities | Higher — update imports/webpack if needed |

Each scenario must state: **files touched**, **parity checks**, **fallow metrics expected to improve**, and **review story** (what reviewer should skim first).

### 4. Implement (small phases)

- One logical change per phase; run tests after each phase
- After moving HTML to Django: JS only builds **context objects** and assigns `innerHTML` / `insertAdjacentHTML` from response
- When generalizing a method, keep old call sites working or update all call sites in the same phase
- Do not expand scope into unrelated templates/backend unless required for parity

### 5. Verify

From `gateway/`:

```bash
npm test
npm run fallow
npx fallow health --format human
bash scripts/fallow-cross-file-dupes.sh
```

If behavior is UI-heavy, run through affected pages (modals, lists, upload, visualizations) per team practice.

### 6. Deliverable for the user

Short summary:

- Chosen scenario and why
- Before/after notes on complexity/dupes (from fallow)
- Files changed
- Manual test checklist (bullet list)
- Any follow-ups (e.g. remove HTML fallbacks left for error paths)

## Refactor heuristics

- **Inline HTML in JS** → identify existing `users/components/*.html`; if none fits, propose **one** new component template (justify why partials/pages are wrong)
- **Duplicate API calls** → shared method on manager or thin wrapper in `core/`
- **Long switch on asset type** → move labels/URLs/permissions into config next to `detailsModalConfig` / `FileListConfig` patterns
- **Complex async chains** → extract steps with clear names; keep orchestration in one place
- **Fallback HTML in `catch`** → prefer a minimal error component template; avoid duplicating full happy-path markup

## Review checklist (for PR description)

- [ ] No new logic in Django templates except initialization
- [ ] No new files under `static/js/` root; new classes in subfolders only
- [ ] No edits under `deprecated/`
- [ ] Cross-file dupes script passes
- [ ] Jest updated or added for changed public behavior
- [ ] Parity: lists, modals, permissions, and error states manually noted

## Additional resources

- Fallow commands and CI hooks: [fallow-gateway.md](fallow-gateway.md)
- Project frontend rules: `.cursor/rules/django_javascript_implementation.mdc`
