/**
 * File / capture list page constants.
 * Migrated from deprecated/file-list.js (CONFIG).
 */
/** Query params for capture list (ListCapturesView GET). */
const CAPTURE_LIST_PARAM_SPECS = [
    { param: "search", elementId: "search-input" },
    { param: "date_start", elementId: "start_date" },
    { param: "date_end", elementId: "end_date" },
    { param: "min_freq", elementId: "centerFreqMinInput" },
    { param: "max_freq", elementId: "centerFreqMaxInput" },
]

window.FileListConfig = { CAPTURE_LIST_PARAM_SPECS }

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        FileListConfig: window.FileListConfig,
        CAPTURE_LIST_PARAM_SPECS,
    }
}
