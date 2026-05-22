# Jest helpers reference (gateway static JS)

## testHelpers.js (primary exports)

| Export | Use when |
|--------|----------|
| `setupStandardUnitTest` | Default start of unit test `beforeEach` |
| `createMockDOMUtils` | Class uses `window.DOMUtils` without modals |
| `createMockDOMUtilsWithModals` | Modal loading/error/open/close |
| `createMockAPIClient` | Inject or assign API client mock |
| `createMockPermissionsManager` | Permission-gated actions |
| `installDocumentGetByIdMap` | Code looks up specific element IDs |
| `installMinimalDocumentMocks` / `installDocumentQueryStubs` | Low-level DOM stubs |
| `mergeWindowMocks` | Attach globals (`downloadActionManager`, etc.) |
| `flushMicrotasks` | Settle `setTimeout(0)` chains |
| `createMockFetchResponse` / `mockFetchResolved` | Raw `fetch` tests |
| `installCsrfMetaToken` | `APIClient` / CSRF paths |
| `createPublishingSubmitDomFixture` | Publish flow DOM |
| `createDefaultAssetSearchConfig` | Search handler tests |

`setupStandardUnitTest` always calls `jest.clearAllMocks()` and installs document stubs; pass `useModalDomUtils: true` for action/modal suites.

## actionTestMocks.js

| Export | Use when |
|--------|----------|
| `setupDownloadActionTestEnvironment` | Download action manager tests |
| `installBootstrapModalMocks` | Any Bootstrap 5 modal interaction |
| `createMockDownloadPermissions` | Download permission checks |
| `createDefaultShareActionConfig` | Share action defaults |

## Example: permission denied

```javascript
setupStandardUnitTest({
	apiClientOverrides: { post: jest.fn().mockResolvedValue({ success: false, message: "Forbidden" }) },
});
const manager = new SomeActionManager({ permissions: { canShare: false } });
await manager.submit();
expect(window.DOMUtils.showError).toHaveBeenCalled();
```

## Example: DOM id map

```javascript
const form = createMockFormElement();
setupStandardUnitTest({
	getElementByIdMap: { "share-form": form },
});
```

## jest.setup.js

Provides baseline `document`, `window`, `fetch`, storage, and timers. Do not duplicate full window mocks in every file—override only what the test needs in `beforeEach`.

## Import paths

From `actions/__tests__/Foo.test.js`:

```javascript
const { setupStandardUnitTest } = require("../../tests-config/testHelpers.js");
```

From `actions/details/__tests__/Bar.test.js`:

```javascript
const { setupStandardUnitTest } = require("../../../tests-config/testHelpers.js");
```

Adjust `../` depth to reach `tests-config/`.
