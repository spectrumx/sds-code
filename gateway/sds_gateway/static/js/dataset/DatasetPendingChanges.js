/**
 * Shared pending capture/file change tables for dataset edit review.
 */
class DatasetPendingChanges {
    static buildRow(id, change, valueKey, entityAttr) {
        return {
            data_attrs: { "change-id": id },
            cells: [
                {
                    kind: "html",
                    tag: "span",
                    class: `badge bg-${change.action === "add" ? "success" : "danger"}`,
                    text: change.action === "add" ? "Add" : "Remove",
                },
                { kind: "text", value: change.data[valueKey] },
            ],
            actions: [
                {
                    label: "Cancel",
                    css_class: "btn-secondary",
                    extra_class: "cancel-change",
                    data_attrs: {
                        [`${entityAttr}-id`]: id,
                        "change-type": entityAttr,
                    },
                },
            ],
        }
    }

    static async renderPendingTable(
        handler,
        {
            listElement,
            countElement,
            entries,
            valueKey,
            entityAttr,
            emptyMessage,
        },
    ) {
        if (entries.length === 0) {
            listElement.innerHTML = `<tr><td colspan="3" class="text-center text-muted">${emptyMessage}</td></tr>`
            if (countElement) {
                countElement.textContent = "0"
            }
            return
        }

        const rows = entries.map(([id, change]) =>
            this.buildRow(id, change, valueKey, entityAttr),
        )

        const success = await window.DOMUtils.renderTable(listElement, rows, {
            empty_message: emptyMessage,
            empty_colspan: 3,
        })

        if (!success) {
            await window.DOMUtils.showMessage("Error loading changes", {
                variant: "danger",
                placement: "replace",
                target: listElement,
                presentation: "table",
                templateContext: { colspan: 3 },
            })
        }

        if (countElement) {
            countElement.textContent = String(entries.length)
        }

        handler.addCancelButtonListeners()
    }
}

window.DatasetPendingChanges = DatasetPendingChanges

if (typeof module !== "undefined" && module.exports) {
    module.exports = { DatasetPendingChanges }
}
