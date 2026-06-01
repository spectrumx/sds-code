/**
 * Shared Jest helpers for static/js tests (DOMUtils mocks, microtask flush).
 */

/** @returns {Record<string, jest.Mock>} */
function createMockDOMUtils(overrides = {}) {
    return {
        show: jest.fn(),
        hide: jest.fn(),
        showMessage: jest.fn().mockResolvedValue(true),
        showVisualizationPanel: jest.fn().mockResolvedValue(true),
        hideVisualizationPanel: jest.fn(),
        showError: jest.fn().mockResolvedValue(true),
        renderLoading: jest.fn().mockResolvedValue(true),
        renderContent: jest.fn().mockResolvedValue(true),
        renderTable: jest.fn().mockResolvedValue(true),
        renderSelectOptions: jest.fn().mockResolvedValue(true),
        renderPagination: jest.fn().mockResolvedValue(true),
        renderDropdown: jest.fn().mockResolvedValue("<div>Mock Dropdown</div>"),
        ...overrides,
    }
}

/** DOMUtils shape used by Share/Download action tests. */
function createMockDOMUtilsWithModals(overrides = {}) {
    return createMockDOMUtils({
        showModalLoading: jest.fn().mockResolvedValue(true),
        clearModalLoading: jest.fn(),
        showModalError: jest.fn().mockResolvedValue(true),
        openModal: jest.fn(),
        closeModal: jest.fn(),
        ...overrides,
    })
}

function installMinimalDocumentMocks() {
    document.getElementById = jest.fn(() => null)
    document.querySelector = jest.fn(() => null)
    document.querySelectorAll = jest.fn(() => [])
}

function installDocumentQueryStubs() {
    document.querySelector = jest.fn(() => null)
    document.querySelectorAll = jest.fn(() => [])
}

/**
 * @param {Record<string, unknown>} idToElement
 */
function installDocumentGetByIdMap(idToElement) {
    document.getElementById = jest.fn((id) => idToElement[id] ?? null)
}

function mergeWindowMocks(overrides = {}) {
    if (typeof global.window === "undefined") {
        global.window = {}
    }
    Object.assign(global.window, overrides)
    return global.window
}

function createMockAPIClient(overrides = {}) {
    return {
        get: jest.fn().mockResolvedValue({ success: true }),
        post: jest.fn().mockResolvedValue({ success: true }),
        request: jest.fn().mockResolvedValue({ success: true }),
        ...overrides,
    }
}

function createMockPermissionsManager(overrides = {}) {
    return {
        userPermissionLevel: "owner",
        isOwner: true,
        currentUserId: 1,
        datasetPermissions: { canEditMetadata: true },
        canEditMetadata: jest.fn(() => true),
        canAddAssets: jest.fn(() => true),
        canRemoveOwnAssets: jest.fn(() => true),
        canRemoveAnyAssets: jest.fn(() => true),
        canShare: jest.fn(() => true),
        canDownload: jest.fn(() => true),
        canView: jest.fn(() => true),
        canAddAsset: jest.fn(() => true),
        canRemoveAsset: jest.fn(() => true),
        ...overrides,
    }
}

function createMockFormElement(extra = {}) {
    return {
        addEventListener: jest.fn(),
        querySelectorAll: jest.fn(() => []),
        ...extra,
    }
}

function createMockButtonElement(extra = {}) {
    return {
        addEventListener: jest.fn(),
        disabled: false,
        ...extra,
    }
}

function createDefaultAssetSearchConfig(overrides = {}) {
    return {
        searchFormId: "search-form",
        searchButtonId: "search-button",
        clearButtonId: "clear-button",
        tableBodyId: "table-body",
        paginationContainerId: "pagination-container",
        confirmFileSelectionId: "confirm-file-selection",
        type: "captures",
        apiEndpoint: "/api/search/",
        formHandler: {
            setSearchHandler: jest.fn(),
            selectedCaptures: new Set(),
            selectedFiles: new Set(),
        },
        isEditMode: false,
        initialFileDetails: {},
        initialCaptureDetails: {},
        ...overrides,
    }
}

function createAssetSearchGetElementByIdMap({
    mockForm,
    mockButton,
    mockTableBody,
}) {
    return {
        "search-form": mockForm,
        "search-button": mockButton,
        "clear-button": mockButton,
        "table-body": mockTableBody,
        "pagination-container": { innerHTML: "" },
        "confirm-file-selection": mockButton,
    }
}

function createDatasetSearchGetElementByIdMap({
    mockForm,
    mockSearchButton,
    mockClearButton,
    mockResultsContainer,
    mockResultsTbody,
    mockResultsCount,
}) {
    return {
        "search-form": mockForm,
        "search-button": mockSearchButton,
        "clear-button": mockClearButton,
        "results-container": mockResultsContainer,
        "results-tbody": mockResultsTbody,
        "results-count": mockResultsCount,
    }
}

function createDefaultDatasetSearchConfig(overrides = {}) {
    return {
        searchFormId: "search-form",
        searchButtonId: "search-button",
        clearButtonId: "clear-button",
        resultsContainerId: "results-container",
        resultsTbodyId: "results-tbody",
        resultsCountId: "results-count",
        ...overrides,
    }
}

/**
 * @param {Record<string, string|null>} getAttributeMap
 */
function createMockWebDownloadButton(getAttributeMap = {}) {
    const mockButton = {
        dataset: { downloadSetup: "false" },
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        getAttribute: jest.fn((attr) => getAttributeMap[attr] ?? null),
        click: jest.fn(),
        disabled: false,
        textContent: "Download",
        innerHTML: "Download",
        parentNode: { replaceChild: jest.fn() },
        cloneNode: jest.fn(),
    }
    mockButton.cloneNode.mockImplementation(() => mockButton)
    return mockButton
}

function createMockWebDownloadModal() {
    return {
        addEventListener: jest.fn(),
        querySelector: jest.fn(),
        querySelectorAll: jest.fn(() => []),
        getAttribute: jest.fn(),
        setAttribute: jest.fn(),
        removeEventListener: jest.fn(),
    }
}

function installWebDownloadDomMocks(mockButton, mockModal) {
    document.querySelector = jest.fn(() => mockButton)
    document.querySelectorAll = jest.fn((selector) =>
        selector === ".web-download-btn" ? [mockButton] : [],
    )
    document.getElementById = jest.fn((id) => {
        if (id.startsWith("webDownloadModal-")) return mockModal
        if (id.startsWith("webDownloadModalLabel-")) return { innerHTML: "" }
        if (id.startsWith("webDownloadDatasetName-")) return { textContent: "" }
        if (id.startsWith("confirmWebDownloadBtn-")) return mockButton
        return null
    })
}

function installMockWindowOrigin(origin = "http://localhost:8000") {
    if (!global.window) {
        global.window = {}
    }
    Object.defineProperty(global.window, "location", {
        value: { origin },
        writable: true,
        configurable: true,
    })
    if (typeof window !== "undefined") {
        Object.defineProperty(window, "location", {
            value: { origin },
            writable: true,
            configurable: true,
        })
    }
}

/**
 * Standard beforeEach: preserve jest.setup globals on window, refresh DOM/API mocks.
 * @param {object} [opts]
 * @param {Record<string, unknown>} [opts.getElementByIdMap]
 * @param {object} [opts.window]
 * @param {object|false} [opts.apiClient] - false to skip APIClient assignment
 * @param {object} [opts.apiClientOverrides]
 */
function setupStandardUnitTest(opts = {}) {
    jest.clearAllMocks()
    installDocumentQueryStubs()
    if (opts.getElementByIdMap) {
        installDocumentGetByIdMap(opts.getElementByIdMap)
    } else {
        installMinimalDocumentMocks()
    }
    const domUtils =
        opts.domUtils ??
        (opts.useModalDomUtils
            ? createMockDOMUtilsWithModals(opts.domUtilsOverrides)
            : createMockDOMUtils(opts.domUtilsOverrides))
    mergeWindowMocks({
        DOMUtils: domUtils,
        ...opts.window,
    })
    if (opts.useModalDomUtils) {
        require("../core/BaseManager.js")
        const { ModalManager } = require("../core/ModalManager.js")
        mergeWindowMocks({ ModalManager, BaseManager: global.BaseManager })
    }
    if (opts.apiClient !== false) {
        const api = createMockAPIClient(opts.apiClientOverrides)
        global.APIClient = api
        mergeWindowMocks({ APIClient: api })
    }
    return { domUtils }
}

function mockDatasetEditingHandlerConfig(overrides = {}) {
    return {
        datasetUuid: "test-dataset-uuid",
        permissions: createMockPermissionsManager(overrides.permissions),
        currentUserId: 1,
        initialCaptures: overrides.initialCaptures ?? [
            { id: 1, name: "Capture 1", type: "drf", owner_id: 1 },
            { id: 2, name: "Capture 2", type: "drf", owner_id: 2 },
        ],
        initialFiles: overrides.initialFiles ?? [
            { id: 1, name: "file1.h5", size: "1.2 MB", owner_id: 1 },
            { id: 2, name: "file2.h5", size: "2.5 MB", owner_id: 2 },
        ],
        ...overrides,
    }
}

function createPermissionsManagerMockInstance() {
    return {
        canEditMetadata: jest.fn(() => true),
        canAddAssets: jest.fn(() => true),
        canRemoveAnyAssets: jest.fn(() => true),
        canRemoveOwnAssets: jest.fn(() => true),
        canShare: jest.fn(() => true),
        canDownload: jest.fn(() => true),
        canView: jest.fn(() => true),
    }
}

function installMockDatasetListLocation() {
    Object.defineProperty(window, "location", {
        value: {
            href: "http://localhost:8000/datasets/",
            pathname: "/datasets/",
            search: "",
        },
        writable: true,
    })
}

function flushMicrotasks() {
    return new Promise((resolve) => setTimeout(resolve, 0))
}

/** @param {object} opts */
function createMockFetchResponse(opts = {}) {
    const {
        ok = true,
        status = ok ? 200 : 404,
        contentType = "application/json",
        jsonData = { success: true },
        textData = "plain text",
        jsonReject,
    } = opts
    const headers = { get: jest.fn(() => contentType) }
    const response = {
        ok,
        status,
        statusText: opts.statusText ?? (ok ? "OK" : "Not Found"),
        headers,
        json: jsonReject
            ? jest.fn().mockRejectedValue(jsonReject)
            : jest.fn().mockResolvedValue(jsonData),
        text: jest.fn().mockResolvedValue(textData),
    }
    return response
}

function mockFetchResolved(mockFetch, responseOpts) {
    mockFetch.mockResolvedValue(createMockFetchResponse(responseOpts))
}

function installMinimalDocumentForApiClient() {
    global.document = {
        querySelector: jest.fn(() => null),
        cookie: "",
    }
}

function installCsrfMetaToken(token = "test-csrf-token") {
    const mockMetaToken = {
        getAttribute: jest.fn(() => token),
    }
    global.document.querySelector = jest.fn((selector) => {
        if (selector === 'meta[name="csrf-token"]') return mockMetaToken
        if (selector === '[name="csrfmiddlewaretoken"]') return null
        return null
    })
    return mockMetaToken
}

function createMockDatasetHandlerInstance(mode = "edit") {
    const base = {
        initialize: jest.fn(),
        setupEventListeners: jest.fn(),
        filesSearchHandler: {
            initialize: jest.fn(),
            search: jest.fn(),
        },
    }
    if (mode === "edit") {
        return {
            ...base,
            loadDatasetData: jest.fn(),
            markCaptureForRemoval: jest.fn(),
            markFileForRemoval: jest.fn(),
            getPendingChanges: jest.fn(),
        }
    }
    return {
        ...base,
        navigateStep: jest.fn(),
        validateCurrentStep: jest.fn(),
        updateReviewStep: jest.fn(),
    }
}

function installDatasetModeHandlerMocks(
    DatasetEditingHandler,
    DatasetCreationHandler,
) {
    const editing = createMockDatasetHandlerInstance("edit")
    const creation = createMockDatasetHandlerInstance("creation")
    DatasetEditingHandler.mockImplementation(() => editing)
    DatasetCreationHandler.mockImplementation(() => creation)
    return { editing, creation }
}

/**
 * DOM fixture for DatasetModeManager publish/submit tests.
 */
function createPublishingSubmitDomFixture(opts = {}) {
    const {
        publicChecked = true,
        statusValue = "final",
        publishToggleChecked = true,
        includePublicOption = true,
        includeStatus = true,
    } = opts
    const submitBtn = document.createElement("button")
    submitBtn.id = "submitForm"
    submitBtn.classList = { contains: jest.fn(() => false) }
    Object.defineProperty(submitBtn, "offsetParent", {
        get: () => submitBtn,
        configurable: true,
    })
    const elements = {
        submitForm: submitBtn,
    }
    if (opts.includePublishToggle !== false) {
        const publishToggle = document.createElement("input")
        publishToggle.id = "publish-dataset-toggle"
        publishToggle.checked = publishToggleChecked
        elements["publish-dataset-toggle"] = publishToggle
    }
    if (includeStatus) {
        const statusField = document.createElement("input")
        statusField.id = "id_status"
        statusField.value = statusValue
        elements.id_status = statusField
    }
    if (includePublicOption) {
        const publicOption = document.createElement("input")
        publicOption.id = "public-option"
        publicOption.checked = publicChecked
        elements["public-option"] = publicOption
    }
    return {
        submitBtn,
        elements,
        install() {
            installDocumentGetByIdMap(elements)
            window.getComputedStyle = jest.fn(() => ({ display: "block" }))
        },
    }
}

function createDatasetModeManagerMockConfig(overrides = {}) {
    return {
        datasetUuid: "test-dataset-uuid",
        userPermissionLevel: "owner",
        currentUserId: 1,
        isOwner: true,
        datasetPermissions: {
            canEditMetadata: true,
            canAddAssets: true,
        },
        ...overrides,
    }
}

module.exports = {
    createMockDOMUtils,
    createMockDOMUtilsWithModals,
    installMinimalDocumentMocks,
    installDocumentQueryStubs,
    installDocumentGetByIdMap,
    mergeWindowMocks,
    createMockAPIClient,
    createMockPermissionsManager,
    createMockFormElement,
    createMockButtonElement,
    createDefaultAssetSearchConfig,
    createAssetSearchGetElementByIdMap,
    createDefaultDatasetSearchConfig,
    createDatasetSearchGetElementByIdMap,
    createMockWebDownloadButton,
    createMockWebDownloadModal,
    installWebDownloadDomMocks,
    installMockWindowOrigin,
    setupStandardUnitTest,
    mockDatasetEditingHandlerConfig,
    createPermissionsManagerMockInstance,
    installMockDatasetListLocation,
    flushMicrotasks,
    createMockFetchResponse,
    mockFetchResolved,
    installMinimalDocumentForApiClient,
    installCsrfMetaToken,
    createMockDatasetHandlerInstance,
    installDatasetModeHandlerMocks,
    createPublishingSubmitDomFixture,
    createDatasetModeManagerMockConfig,
}
