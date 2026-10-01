/**
 * Controls filtering, sorting, and pagination on the pending downloads page.
 */
class PendingDownloadsListController {
    constructor(config = {}) {
        this.form = document.getElementById(
            config.formId || "downloads-filter-form",
        )
        this.statusFilter = document.getElementById(
            config.statusFilterId || "download-status-filter",
        )
        this.startDateFilter = document.getElementById(
            config.startDateFilterId || "created-at-start-filter",
        )
        this.endDateFilter = document.getElementById(
            config.endDateFilterId || "created-at-end-filter",
        )
        this.createdSortHeader = document.getElementById(
            config.createdSortHeaderId || "created-sort-header",
        )
        this.pagination = document.getElementById(
            config.paginationId || "downloads-pagination",
        )
        this.navigate =
            config.navigate ||
            ((url) => {
                window.location.assign(url)
            })
        this.location = config.location || window.location

        this.initialize()
    }

    initialize() {
        for (const filter of [
            this.statusFilter,
            this.startDateFilter,
            this.endDateFilter,
        ]) {
            filter?.addEventListener("change", () => this.applyFilters())
        }

        this.form?.addEventListener("submit", (event) => {
            event.preventDefault()
            this.applyFilters()
        })
        this.createdSortHeader?.addEventListener("click", () =>
            this.toggleCreatedSort(),
        )
        this.createdSortHeader?.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return
            event.preventDefault()
            this.toggleCreatedSort()
        })
        this.pagination?.addEventListener("click", (event) => {
            const link = event.target.closest("[data-page]")
            if (!link) return
            event.preventDefault()
            this.navigateToPage(link.dataset.page)
        })
    }

    applyFilters() {
        const params = this.currentSearchParams()
        this.setOptionalParam(params, "status", this.statusFilter?.value)
        this.setOptionalParam(
            params,
            "created_at_start",
            this.startDateFilter?.value,
        )
        this.setOptionalParam(
            params,
            "created_at_end",
            this.endDateFilter?.value,
        )
        params.set("page", "1")
        this.navigateWithParams(params)
    }

    toggleCreatedSort() {
        const params = this.currentSearchParams()
        const isCreatedSort = params.get("sort_by") === "created_at"
        const currentOrder = params.get("sort_order")
        const newOrder =
            isCreatedSort && currentOrder === "desc" ? "asc" : "desc"

        params.set("sort_by", "created_at")
        params.set("sort_order", newOrder)
        params.set("page", "1")
        this.navigateWithParams(params)
    }

    navigateToPage(page) {
        const params = this.currentSearchParams()
        params.set("page", String(page))
        this.navigateWithParams(params)
    }

    currentSearchParams() {
        return new URLSearchParams(this.location.search.replace(/^\?/, ""))
    }

    setOptionalParam(params, name, value) {
        if (value) {
            params.set(name, value)
        } else {
            params.delete(name)
        }
    }

    navigateWithParams(params) {
        const queryString = params.toString()
        const url = queryString
            ? `${this.location.pathname}?${queryString}`
            : this.location.pathname
        this.navigate(url)
    }
}

if (typeof window !== "undefined") {
    window.PendingDownloadsListController = PendingDownloadsListController
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = PendingDownloadsListController
}
