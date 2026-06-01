/**
 * Shared mocks for action manager tests (Download, Share, Versioning).
 */

const {
    setupStandardUnitTest,
    createMockWebDownloadButton,
    createMockWebDownloadModal,
    installWebDownloadDomMocks,
} = require("../../tests-config/testHelpers.js")

function installBootstrapModalMocks() {
    global.bootstrap = {
        Modal: jest.fn().mockImplementation(() => ({
            show: jest.fn(),
            hide: jest.fn(),
        })),
    }
    global.bootstrap.Modal.getInstance = jest.fn(() => ({
        hide: jest.fn(),
    }))
}

function createMockDownloadPermissions(overrides = {}) {
    return {
        canDownload: jest.fn(() => true),
        ...overrides,
    }
}

/**
 * @param {object} [opts]
 * @param {object} [opts.apiClientOverrides]
 * @param {Record<string, string|null>} [opts.buttonAttributes]
 */
function setupDownloadActionTestEnvironment(opts = {}) {
    const mockPermissions = createMockDownloadPermissions(opts.permissions)
    setupStandardUnitTest({
        useModalDomUtils: true,
        apiClientOverrides: {
            post: jest.fn().mockResolvedValue({
                success: true,
                message: "Download request submitted successfully!",
            }),
            ...opts.apiClientOverrides,
        },
        window: {
            fetch: jest.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () =>
                        Promise.resolve({
                            success: true,
                            message: "Download requested",
                        }),
                }),
            ),
            showMessage: jest.fn().mockResolvedValue(true),
            ...opts.window,
        },
    })
    const mockButton = createMockWebDownloadButton({
        "data-item-uuid": "test-dataset-uuid",
        "data-item-type": "dataset",
        ...opts.buttonAttributes,
    })
    const mockModal = createMockWebDownloadModal()
    installWebDownloadDomMocks(mockButton, mockModal)
    installBootstrapModalMocks()
    return { mockPermissions, mockButton, mockModal }
}

function createDefaultShareActionConfig(overrides = {}) {
    return {
        itemUuid: "test-uuid",
        itemType: "dataset",
        permissions: {
            canShare: true,
        },
        ...overrides,
    }
}

function setupShareActionStandardTest(apiClientOverrides = {}) {
    setupStandardUnitTest({
        useModalDomUtils: true,
        apiClientOverrides: {
            get: jest.fn().mockResolvedValue([]),
            ...apiClientOverrides,
        },
    })
}

function createShareSearchTestContext(ShareActionManager, overrides = {}) {
    const mockAPIClient = {
        get: jest.fn(),
        post: jest.fn(),
        ...overrides.apiClient,
    }
    global.window.APIClient = mockAPIClient
    const mockDropdown = {
        querySelector: jest.fn(() => ({
            innerHTML: "",
        })),
    }
    const shareManager = new ShareActionManager({
        itemUuid: "test-uuid",
        itemType: "dataset",
        permissions: {},
        ...overrides.managerConfig,
    })
    shareManager.displayResults = jest.fn()
    shareManager.displayError = jest.fn()
    shareManager.showDropdown = jest.fn()
    return { mockAPIClient, mockDropdown, shareManager }
}

function createMockVersionCreateButton(
    datasetUuid = "test-dataset-uuid",
    extra = {},
) {
    return {
        id: `createVersionBtn-${datasetUuid}`,
        dataset: { versionSetup: "false", processing: "false" },
        addEventListener: jest.fn(),
        disabled: false,
        click: jest.fn(),
        ...extra,
    }
}

function createVersioningActionConfig(overrides = {}) {
    const datasetUuid = overrides.datasetUuid ?? "test-dataset-uuid"
    const mockPermissions = {
        canEditMetadata: jest.fn(() => true),
        canShare: jest.fn(() => true),
        ...(overrides.permissions || {}),
    }
    return {
        config: {
            datasetUuid,
            permissions: mockPermissions,
            ...overrides.config,
        },
        mockPermissions,
        datasetUuid,
    }
}

function setupVersioningActionTestEnvironment(overrides = {}) {
    jest.clearAllMocks()
    const { config, mockPermissions, datasetUuid } =
        createVersioningActionConfig(overrides)
    const mockButton = createMockVersionCreateButton(
        datasetUuid,
        overrides.button,
    )
    setupStandardUnitTest({
        useModalDomUtils: true,
        getElementByIdMap: {
            [`createVersionBtn-${datasetUuid}`]: mockButton,
        },
        apiClientOverrides: {
            post: jest.fn().mockResolvedValue({
                success: true,
                version: 2,
            }),
            ...overrides.apiClientOverrides,
        },
        window: {
            listRefreshManager: {
                loadTable: jest.fn().mockResolvedValue(true),
            },
            location: {
                reload: jest.fn(),
            },
            ...overrides.window,
        },
    })
    return { mockConfig: config, mockPermissions, mockButton, datasetUuid }
}

function createVersionCreationClickEvent() {
    return {
        preventDefault: jest.fn(),
        stopPropagation: jest.fn(),
    }
}

const LIST_REFRESH_SEP = "<!-- LIST_REFRESH_SEP -->"

/**
 * @param {{ tableHtml?: string, modalsHtml?: string }} parts
 */
function createListRefreshResponseHtml(parts = {}) {
    const tableHtml = parts.tableHtml ?? "<table><tbody></tbody></table>"
    const modalsHtml = parts.modalsHtml ?? ""
    if (!modalsHtml) return tableHtml
    return `${tableHtml}${LIST_REFRESH_SEP}${modalsHtml}`
}

/**
 * @param {{ tableId?: string, modalsId?: string }} ids
 */
function installListRefreshDomContainers(ids = {}) {
    const tableId = ids.tableId ?? "dataset-list-ajax-wrapper"
    const modalsId = ids.modalsId ?? "dataset-modals-container"
    document.body.innerHTML = ""
    const table = document.createElement("div")
    table.id = tableId.replace(/^#/, "")
    const modals = document.createElement("div")
    modals.id = modalsId.replace(/^#/, "")
    document.body.append(table, modals)
    return {
        table,
        modals,
        tableSelector: `#${table.id}`,
        modalsSelector: `#${modals.id}`,
    }
}

module.exports = {
    installBootstrapModalMocks,
    createMockDownloadPermissions,
    setupDownloadActionTestEnvironment,
    createDefaultShareActionConfig,
    setupShareActionStandardTest,
    createShareSearchTestContext,
    createMockVersionCreateButton,
    createVersioningActionConfig,
    setupVersioningActionTestEnvironment,
    createVersionCreationClickEvent,
    LIST_REFRESH_SEP,
    createListRefreshResponseHtml,
    installListRefreshDomContainers,
}
