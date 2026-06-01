---
name: jest-test-writing
description: Writes and refactors Jest unit tests for browser JS (jsdom), emphasizing behavior-focused tests, shared mocks, and repo conventions. Use when adding or updating tests under gateway/sds_gateway/static/js, fixing failing Jest runs, or when the user asks for Jest test best practices.
---

# Jest test writing (SDS gateway static JS)

## When to apply

- New or changed code under `gateway/sds_gateway/static/js/`
- User asks for Jest patterns, test structure, or coverage for frontend managers/handlers
- CI/local failure from `npm test` in `gateway/`

## Run tests

From `gateway/`:

```bash
npm test
npm run test:watch
npm run test:coverage
```

Config: `sds_gateway/static/js/tests-config/jest.config.js` (jsdom, `clearMocks` + `restoreMocks`).

## File placement

| Rule | Detail |
|------|--------|
| Co-locate | `SomeManager.js` → `__tests__/SomeManager.test.js` in the same folder |
| Naming | `*.test.js` or `*.spec.js` (see `testMatch` in jest config) |
| Skip | Never add tests for `deprecated/` |

## What to test (and what not to)

## Do

- Public methods and user-visible outcomes (DOM updates, calls to `DOMUtils`, `APIClient`, Bootstrap modal show/hide)
- Branches that encode product rules (permissions denied, missing modal, API error responses)
- Async flows: `await` the method under test, then assert mocks/callbacks

## Avoid

- Asserting private helpers or internal call order unless order is the contract
- Tests that only `expect(x).toBeDefined()` or mirror the implementation line-for-line
- Copy-pasting 50-line mock trees—extend shared helpers instead

## Shared infrastructure (use first)

Read and reuse before inventing mocks:

| Resource | Path |
|----------|------|
| DOM/API/permissions helpers | `sds_gateway/static/js/tests-config/testHelpers.js` |
| Action-manager setups | `sds_gateway/static/js/__tests__/helpers/actionTestMocks.js` |
| Global env | `sds_gateway/static/js/tests-config/jest.setup.js` |

Common helpers:

- `setupStandardUnitTest({ useModalDomUtils, apiClientOverrides, window, getElementByIdMap })` — resets mocks, stubs `document`, sets `window.DOMUtils`
- `createMockDOMUtils` / `createMockDOMUtilsWithModals`
- `createMockAPIClient`, `createMockPermissionsManager`
- `flushMicrotasks()` — after fire-and-forget promises tied to `setTimeout(0)`
- `installDocumentGetByIdMap({ id: element })` when code uses `getElementById`

For Download/Share/Versioning action tests, prefer `setupDownloadActionTestEnvironment` / patterns in `actionTestMocks.js`.

## Structure template

```javascript
/**
 * Jest tests for TargetClass
 */

import { TargetClass } from "../TargetClass.js";
import { setupStandardUnitTest, flushMicrotasks } from "../../tests-config/testHelpers.js";

describe("TargetClass", () => {
	beforeEach(() => {
		setupStandardUnitTest({ /* opts */ });
		// Extra per-suite: bootstrap, document.body, window globals
	});

	test("describes behavior in plain language", async () => {
		// arrange → act → assert
	});
});
```

Use `require()` for helpers if the file already uses CommonJS; stay consistent within a file.

## Mocking conventions (this repo)

1. **Bootstrap modals** — set `global.bootstrap.Modal` and `Modal.getInstance` in `beforeEach` (see `ModalManager.test.js`, `actionTestMocks.installBootstrapModalMocks`).
2. **`window.DOMUtils`** — via `setupStandardUnitTest` or explicit assign; use `.mockResolvedValue()` for async UI helpers.
3. **`document`** — prefer `installDocumentGetByIdMap` or minimal stubs from testHelpers; use real `document.createElement` / `body.innerHTML` only when testing DOM wiring.
4. **Module mocks** — `jest.mock("../Dependency.js")` at top level; factory returns minimal surface the unit needs.
5. **Fetch / API** — mock `APIClient` methods or `window.fetch` with `createMockFetchResponse` / resolved shapes `{ success: true }` matching production handlers.

## Async

- Prefer `async/await` in tests over bare `.then()`.
- If code schedules work on microtasks/macrotasks without returning a promise, `await flushMicrotasks()` before assertions.
- Fake timers: use `jest.useFakeTimers()` only when testing timer logic; restore in `afterEach`.

## Assertions

- One logical behavior per test name (readable as a spec sentence).
- Assert on **arguments** to mocks when the contract is “calls X with Y” (`toHaveBeenCalledWith`).
- For errors: assert rejected promise or that `showError` / `showModalError` was invoked with expected message.

## Coverage

Global thresholds (70%) in jest config. New code should not drop coverage on touched files; add tests for new branches rather than excluding files.

## Checklist before finishing

- [ ] Test file lives in `__tests__/` next to source
- [ ] Reused `testHelpers` / `actionTestMocks` where applicable
- [ ] `beforeEach` resets DOM/globals needed for isolation
- [ ] Tests describe behavior, not implementation trivia
- [ ] `npm test` passes from `gateway/`

## More detail

See [reference.md](reference.md) for helper exports and example patterns.
