/**
 * Quick-add capture(s) to dataset API helpers (shared by QuickAddToDatasetManager).
 */

/**
 * @param {string} quickAddUrl
 * @param {string} datasetUuid
 * @param {string} captureUuid
 * @returns {Promise<{ added: number, skipped: number, errors: string[], success: boolean }>}
 */
async function postQuickAddCapture(quickAddUrl, datasetUuid, captureUuid) {
    const response = await window.APIClient.post(
        quickAddUrl,
        {
            dataset_uuid: datasetUuid,
            capture_uuid: captureUuid,
        },
        null,
        true,
    )
    if (!response.success) {
        return {
            added: 0,
            skipped: 0,
            errors: [response.error || "Request failed"],
            success: false,
        }
    }
    return {
        added: response.added?.length ?? 0,
        skipped: response.skipped?.length ?? 0,
        errors: [...(response.errors || [])],
        success: true,
    }
}

/**
 * @param {string} quickAddUrl
 * @param {string} datasetUuid
 * @param {string[]} captureUuids
 */
async function postQuickAddCaptures(quickAddUrl, datasetUuid, captureUuids) {
    let totalAdded = 0
    let totalSkipped = 0
    const errorMessages = []
    for (const captureUuid of captureUuids) {
        try {
            const result = await postQuickAddCapture(
                quickAddUrl,
                datasetUuid,
                captureUuid,
            )
            if (result.success) {
                totalAdded += result.added
                totalSkipped += result.skipped
                if (result.errors.length) {
                    errorMessages.push(...result.errors)
                }
            } else {
                errorMessages.push(...result.errors)
            }
        } catch (err) {
            errorMessages.push(err?.data?.error || err?.message || String(err))
        }
    }
    return { totalAdded, totalSkipped, errorMessages }
}

/**
 * Build a concise summary from quick-add counts.
 */
function formatQuickAddSummary(added, skipped, failedCount, firstErrorMessage) {
    const parts = []
    if (added > 0) parts.push(`${added} added`)
    if (skipped > 0) parts.push(`${skipped} already in dataset`)
    if (failedCount > 0) {
        parts.push(`${failedCount} failed`)
        if (firstErrorMessage != null) {
            const text = String(firstErrorMessage)
            if (text) parts.push(`: ${text}`)
        }
    }
    return parts.length ? `${parts.join(", ")}.` : "Done."
}

if (typeof window !== "undefined") {
    window.QuickAddApi = {
        postQuickAddCapture,
        postQuickAddCaptures,
        formatQuickAddSummary,
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        postQuickAddCapture,
        postQuickAddCaptures,
        formatQuickAddSummary,
    }
}
