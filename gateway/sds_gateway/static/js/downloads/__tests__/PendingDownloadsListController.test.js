/**
 * Jest tests for PendingDownloadsListController.
 */

const PendingDownloadsListController = require("../PendingDownloadsListController.js")

describe("PendingDownloadsListController", () => {
    let navigate
    let location

    beforeEach(() => {
        document.body.innerHTML = `
            <form id="downloads-filter-form">
                <select id="download-status-filter">
                    <option value="">All</option>
                    <option value="Ready">Ready</option>
                </select>
                <input id="created-at-start-filter" type="date">
                <input id="created-at-end-filter" type="date">
            </form>
            <table>
                <thead>
                    <tr>
                        <th id="created-sort-header" tabindex="0">Created</th>
                    </tr>
                </thead>
            </table>
            <nav id="downloads-pagination">
                <a href="?page=2" data-page="2"><span>Next</span></a>
            </nav>
        `
        location = {
            pathname: "/users/downloads/",
            search: "?sort_by=created_at&sort_order=asc&page=3",
        }
        navigate = jest.fn()
    })

    test("filter changes navigate with all filters and reset the page", () => {
        const controller = new PendingDownloadsListController({
            navigate,
            location,
        })
        controller.statusFilter.value = "Ready"
        controller.startDateFilter.value = "2026-09-01"
        controller.endDateFilter.value = "2026-09-30"

        controller.statusFilter.dispatchEvent(new Event("change"))

        expect(navigate).toHaveBeenCalledWith(
            "/users/downloads/?sort_by=created_at&sort_order=asc&page=1&status=Ready&created_at_start=2026-09-01&created_at_end=2026-09-30",
        )
    })

    test("clearing filters removes them from the query string", () => {
        location.search = "?status=Ready&created_at_start=2026-09-01&page=2"
        const controller = new PendingDownloadsListController({
            navigate,
            location,
        })

        controller.applyFilters()

        expect(navigate).toHaveBeenCalledWith("/users/downloads/?page=1")
    })

    test("created sort toggles direction and resets the page", () => {
        location.search =
            "?status=Ready&sort_by=created_at&sort_order=desc&page=2"
        const controller = new PendingDownloadsListController({
            navigate,
            location,
        })

        controller.createdSortHeader.click()

        expect(navigate).toHaveBeenCalledWith(
            "/users/downloads/?status=Ready&sort_by=created_at&sort_order=asc&page=1",
        )
    })

    test("keyboard activation sorts by created date", () => {
        const controller = new PendingDownloadsListController({
            navigate,
            location,
        })

        controller.createdSortHeader.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Enter" }),
        )

        expect(navigate).toHaveBeenCalledWith(
            "/users/downloads/?sort_by=created_at&sort_order=desc&page=1",
        )
    })

    test("pagination preserves filters and sorting", () => {
        location.search =
            "?status=Ready&sort_by=created_at&sort_order=desc&page=1"
        new PendingDownloadsListController({ navigate, location })

        document.querySelector("[data-page] span").click()

        expect(navigate).toHaveBeenCalledWith(
            "/users/downloads/?status=Ready&sort_by=created_at&sort_order=desc&page=2",
        )
    })
})
