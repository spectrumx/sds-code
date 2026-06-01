/**
 * Read dataset metadata fields from the create/edit form for change tracking.
 */

function readDatasetNameField(isEditMode, config) {
    const nameField = document.getElementById("id_name")
    if (nameField) {
        return nameField.value || "Untitled Dataset"
    }
    if (!isEditMode) {
        return "Untitled Dataset"
    }
    const readonlyNameField = document.querySelector("input[readonly][value]")
    return (
        readonlyNameField?.value ||
        config.existingDatasetName ||
        "Untitled Dataset"
    )
}

function readDatasetStatusField(isEditMode, config) {
    const statusField = document.getElementById("id_status")
    if (statusField) {
        const statusValue = statusField.value || "draft"
        return statusValue === "final" ? "Final" : "Draft"
    }
    if (!isEditMode) {
        return "Draft"
    }
    const statusBadge = document.getElementById("current-status-badge")
    if (statusBadge?.textContent) {
        return statusBadge.textContent.trim()
    }
    return config.existingDatasetStatus || "Unknown"
}

function readDatasetDescriptionField(isEditMode, config) {
    const descriptionField = document.getElementById("id_description")
    if (descriptionField) {
        return descriptionField.value || "No description provided."
    }
    if (!isEditMode) {
        return "No description provided."
    }
    const readonlyDescField = document.querySelector("textarea[readonly]")
    return (
        readonlyDescField?.value ||
        config.existingDatasetDescription ||
        "No description provided."
    )
}

function readDatasetAuthorsField(isEditMode, config) {
    const authorsField = document.getElementById("id_authors")
    if (!authorsField) {
        return isEditMode ? config.initialAuthors || [] : []
    }
    try {
        return JSON.parse(authorsField.value || "[]")
    } catch {
        return []
    }
}

/**
 * @param {boolean} isEditMode
 * @param {object} config - DatasetModeManager config
 */
function captureDatasetFormSnapshot(isEditMode, config) {
    return {
        name: readDatasetNameField(isEditMode, config),
        status: readDatasetStatusField(isEditMode, config),
        description: readDatasetDescriptionField(isEditMode, config),
        authors: readDatasetAuthorsField(isEditMode, config),
    }
}

if (typeof window !== "undefined") {
    window.captureDatasetFormSnapshot = captureDatasetFormSnapshot
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        captureDatasetFormSnapshot,
        readDatasetNameField,
        readDatasetStatusField,
        readDatasetDescriptionField,
        readDatasetAuthorsField,
    }
}
