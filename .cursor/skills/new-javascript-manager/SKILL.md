---
name: new-javascript-manager
description: Plans SDS gateway web UI features by decomposing user interactions into JavaScript manager methods and a shared implementation todo. Use when adding a new manager, action flow, or modal workflow under gateway/sds_gateway/static/js, or when the user asks to design or implement a new web UI feature interactively.
---

# New JavaScript manager (UX → methods → todo)

## Goal

Before writing code, **walk through the feature with the user** as a numbered user journey. Each step becomes one or more manager methods, DOM hooks, and (if needed) backend/API tasks. Deliver an agreed **markdown todo list** the agent and user follow for implementation.

Do **not** start implementation until the todo list reflects the full flow and the user confirms (or explicitly says to proceed).

## When to apply

- New `*Manager.js` under `gateway/sds_gateway/static/js/` (especially `actions/`)
- Extending an existing manager with a new multi-step UI flow
- User says "new feature", "new action", "modal for…", or attaches this skill

## Project conventions (mandatory)

Follow `.cursor/rules/django_javascript_implementation.mdc`:

- Logic in **separate `.js` files**; templates only **initialize** managers
- New classes in a **subfolder** of `js/` (e.g. `actions/`), not flat `js/`
- Dynamic HTML via Django **`components/`** + `RenderHTMLFragmentView` + `APIClient`; **no HTML strings in JS**
- Reuse `BaseManager`, `ModalManager`, `DOMUtils`, `APIClient`, existing controllers (e.g. `UserInputController`) before adding parallel code
- Ignore `deprecated/`

Reference implementations: `ShareActionManager`, `PublishActionManager`, `DownloadActionManager` in `actions/`.

## Collaborative workflow

Copy this checklist and update it in the chat (or write `docs/features/<feature-slug>-todo.md` only if the user asks for a file):

```text
Planning progress:
- [ ] Name feature, entry point(s), and asset/page scope
- [ ] Draft numbered user journey (happy path)
- [ ] Add error/cancel/back paths per step
- [ ] Map each step → methods + state + DOM/API
- [ ] Identify reuse vs new JS/template/view/API
- [ ] User confirms todo list
- [ ] Implement in todo order
```

### Phase 1 — Discovery (with the user)

Ask or infer, one topic at a time when unclear:

1. **Where** does the user start? (page, row action, dropdown, keyboard)
2. **What** opens next? (modal, inline panel, new route)
3. **Permissions** — who can see/use the action?
4. **Persistence** — what API runs on confirm, and what UI updates after success?
5. **Configuration** — should behavior differ by asset type via config, not duplicated methods?

Use `AskQuestion` when multiple valid UX choices exist.

### Phase 2 — Numbered user journey

Write steps in **present tense, user-visible behavior** (not implementation):

```markdown
## User journey: [Feature name]

1. User …
2. User …
…
```

Include for each step when relevant:

- Visible UI change (modal open, disabled button, spinner)
- Validation / limits (max results, debounce, partial match rules)
- Default vs optional inputs
- Cancel / dismiss behavior

### Phase 3 — Map steps to manager design

For each journey step, extend this table (empty cells mean "none"):

| Step | User action | UI state after | Manager method(s) | DOM / selectors | State on `this` | API / fragment |
|------|-------------|----------------|-------------------|-----------------|-----------------|----------------|
| 1 | … | … | `initialize…` / `setup…` | `#…`, `.…` | … | … |

**Naming patterns** (match existing managers):

| Responsibility | Typical names |
|----------------|---------------|
| Wire clicks/inputs once | `initializeEventListeners`, `setupModalEventHandlers`, `setupSearchInput` |
| Single control binding | `setupShareItem`, `setupRemoveUserButtons` |
| Event handler / submit | `handleShareItem`, `handlePermissionChange` |
| Async server work | `searchUsers`, `handleShareItem` (API + refresh) |
| Render/update UI | `renderChips`, `displayResults`, `updateSaveButtonState` |
| Small internal helpers | `_commitViewerSelection` (leading `_` if not part of public surface) |

**Class shape:**

- Extend `ModalManager` when the flow uses Bootstrap modals; otherwise `BaseManager`
- `constructor(config)` — store ids, permissions, debounce handles, pending change maps
- Call `initializeEventListeners()` from constructor
- Prefer **configuration-driven** branches over copy-paste per asset type

### Phase 4 — Implementation todo (deliverable)

After mapping, output this template filled in for the feature:

```markdown
# [Feature name] — implementation todo

## Summary

[One paragraph: what the user can do and where]

## User journey

1. …
2. …

## Manager: `[ClassName]` (`[path/to/Class].js`)

- [ ] Create class extending `[BaseManager|ModalManager]`
- [ ] `constructor(config)` — …
- [ ] `initializeEventListeners()` — …
- [ ] Step N: `[methodName]` — …
- [ ] …

## Templates & init

- [ ] Page/partial: `[template]` — script tags + `new ClassName({…})`
- [ ] Modal/partial: `[partial]` — markup only, no inline logic
- [ ] Component fragment (if dynamic): `[component]` + view context

## Backend (if needed)

- [ ] Endpoint / view: …
- [ ] Permissions: …

## Tests

- [ ] `__tests__/[ClassName].test.js` — critical paths per journey step (see `.cursor/skills/jest-test-writing/SKILL.md`)

## Done when

- [ ] Happy path matches journey
- [ ] Errors toasts / disabled states documented in journey
- [ ] Page shows updated data after confirm (refresh, fragment, or DOM patch)
```

Mark items `- [x]` only as they ship.

## Canonical example — Share

Use this as the pattern for decomposition (reference: `actions/ShareActionManager.js`).

| Step | User action | Methods / systems |
|------|-------------|-------------------|
| 1 | Opens asset dropdown | Page markup + existing list handlers (often outside share manager) |
| 2 | Chooses Share | Opens modal (`ModalManager` / Bootstrap) |
| 3 | Share modal visible | `setupModalEventHandlers` — resolve modal id, bind controls |
| 4 | Types name/email in search | `setupSearchInput` → `UserInputController`; debounce; `searchUsers`; `displayResults` / `displayError`; limits via API + dropdown UI |
| 5 | Picks a user from results | `selectUser`, `navigateDropdown`; may `checkUserInGroup` |
| 6 | Sets permission | `handlePermissionChange`, `handlePermissionLevelChange`, `updateDropdownMenu`; `pendingPermissionChanges` |
| 7 | Confirms | `setupShareItem` → `handleShareItem`; `updateSaveButtonState` |
| 8 | UI reflects new shares | API success → refresh chips/list, `clearSelections`, toasts; optional notify via `setupNotifyCheckbox` |

When planning a **new** feature, mirror this granularity: search/debounce, pending vs committed state, confirm button gating, and post-success refresh are separate todo items.

## Agent behavior

1. **Collaborate first** — propose journey v1, ask user to correct missing steps
2. **One revision at a time** — update table + todo after user feedback
3. **Reuse explicitly** — name existing classes/methods to extend instead of duplicating
4. **Implement only after confirmation** — then work the todo top-to-bottom; say which item you are on
5. **Large refactors** — after implementation plan is stable, optional pass with `.cursor/skills/gateway-static-js-refactor/SKILL.md`

## Anti-patterns

- Skipping the journey and jumping straight to a new 500-line manager
- Putting business logic or HTML generation in Django templates beyond init
- One giant `handleEverything()` instead of one method per user step
- Duplicate search/modal patterns when `UserInputController` / `ModalManager` already apply
