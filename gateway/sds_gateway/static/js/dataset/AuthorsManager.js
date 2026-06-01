/**
 * Shared author list formatting and DOM readback for dataset flows.
 */
class AuthorsManager {
    /**
     * @param {unknown[]} authors
     * @returns {string}
     */
    static formatAuthors(authors) {
        if (!Array.isArray(authors) || authors.length === 0) {
            return "No authors specified."
        }

        return authors
            .map((author) =>
                typeof author === "string" ? author : author.name || "Unknown",
            )
            .join(", ")
    }

    /**
     * @returns {{ name: string, orcid_id: string, _stableId: string }[]}
     */
    static parseAuthorsFromHiddenField(value) {
        if (!value || String(value).trim() === "") {
            return []
        }
        try {
            return JSON.parse(value)
        } catch (e) {
            console.error("Error parsing initial authors:", e)
            return []
        }
    }

    static normalizeAuthorEntries(authors) {
        return authors.map((author) => {
            if (typeof author === "string") {
                return { name: author, orcid_id: "" }
            }
            return author
        })
    }

    static ensureDefaultAuthorIfEmpty(authors) {
        if (authors.length > 0) {
            return authors
        }
        const currentUserName =
            document.body.dataset.currentUserName || "Current User"
        const currentUserOrcid = document.body.dataset.currentUserOrcid || ""
        return [
            {
                name: currentUserName,
                orcid_id: currentUserOrcid,
            },
        ]
    }

    static ensureAuthorRecord(authors, index) {
        if (!authors[index] || typeof authors[index] === "string") {
            authors[index] = {
                name: typeof authors[index] === "string" ? authors[index] : "",
                orcid_id: "",
            }
        }
        return authors[index]
    }

    static buildAuthorRenderContext(authors, opts = {}) {
        const removed = new Set(opts.removedIndices || [])
        return authors.map((author, index) => {
            const authorName =
                typeof author === "string" ? author : author.name || ""
            const authorOrcid =
                typeof author === "string" ? "" : author.orcid_id || ""
            const stableId = author._stableId || `author-${index}-${Date.now()}`
            if (!author._stableId) {
                author._stableId = stableId
            }
            return {
                index,
                name: authorName,
                orcid_id: authorOrcid,
                stable_id: stableId,
                is_primary: index === 0,
                is_marked_for_removal: removed.has(index),
            }
        })
    }

    static removeTrailingEmptyAuthor(authors, index) {
        if (
            index > 0 &&
            !authors[index].name.trim() &&
            !authors[index].orcid_id.trim()
        ) {
            authors.splice(index, 1)
            return true
        }
        return false
    }

    static notifyReviewDisplay() {
        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    static focusAuthorNameInput(authorsList, index) {
        const newInput = authorsList.querySelector(
            `input[data-index="${index}"][data-field="name"]`,
        )
        if (newInput) {
            newInput.focus()
        }
    }

    /** @param {object} handler - Dataset create/edit handler (BaseManager) */
    static async refreshAuthorsList(
        handler,
        {
            authorsList,
            authorsHiddenField,
            authors,
            addAuthorBtn,
            removedIndices = [],
            addButtonMode = "always",
        },
    ) {
        try {
            const normalizedAuthors = AuthorsManager.buildAuthorRenderContext(
                authors,
                {
                    removedIndices,
                },
            )
            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template: "users/components/author_list_items.html",
                    context: { authors: normalizedAuthors },
                },
                null,
                true,
            )
            if (response.html) {
                authorsList.innerHTML = response.html
            }
        } catch (error) {
            handler.logError?.(error, authorsList)
            await handler.showMessageInTarget(
                "Error loading authors",
                authorsList,
                {
                    variant: "danger",
                    presentation: "alert",
                    templateContext: { icon: "exclamation-triangle" },
                },
            )
        }

        authorsHiddenField.value = JSON.stringify(authors)

        if (addAuthorBtn) {
            if (addButtonMode === "permission") {
                if (handler.permissions?.canEditMetadata) {
                    window.DOMUtils.show(addAuthorBtn)
                } else {
                    window.DOMUtils.hide(addAuthorBtn)
                }
            } else {
                window.DOMUtils.show(addAuthorBtn)
            }
        }
    }

    static detectInitialAuthorChanges(authors, originalAuthors) {
        const authorChanges = { added: [], removed: [], modified: {} }
        if (originalAuthors.length === 0) {
            return authorChanges
        }

        for (const [index, author] of authors.entries()) {
            const authorName = typeof author === "string" ? author : author.name
            const authorOrcid =
                typeof author === "string" ? "" : author.orcid_id
            const existsInOriginal = originalAuthors.some((origAuthor) => {
                const origName =
                    typeof origAuthor === "string"
                        ? origAuthor
                        : origAuthor.name
                const origOrcid =
                    typeof origAuthor === "string" ? "" : origAuthor.orcid_id
                return origName === authorName && origOrcid === authorOrcid
            })
            if (!existsInOriginal) {
                authorChanges.added.push(index)
            }
        }

        for (const [, origAuthor] of originalAuthors.entries()) {
            const origName =
                typeof origAuthor === "string" ? origAuthor : origAuthor.name
            const existsInCurrent = authors.some((author) => {
                const authorName =
                    typeof author === "string" ? author : author.name
                return authorName === origName
            })
            if (!existsInCurrent) {
                const currentIndex = authors.findIndex((author) => {
                    const authorName =
                        typeof author === "string" ? author : author.name
                    return authorName === origName
                })
                if (currentIndex >= 0) {
                    authorChanges.removed.push(currentIndex)
                }
            }
        }

        return authorChanges
    }

    static bindFileTreeModalHandlers(handler) {
        const modal = document.getElementById("fileTreeModal")
        if (!modal) return
        modal.addEventListener("show.bs.modal", () => {
            handler.onFileModalShow()
        })
        modal.addEventListener("hidden.bs.modal", () => {
            handler.onFileModalHide()
        })
    }

    static getCurrentAuthorsWithDOMIds() {
        const authorsList = document.querySelector(".authors-list")
        const currentAuthors = []

        if (authorsList) {
            const authorItems = authorsList.querySelectorAll(
                ".author-item:not(.marked-for-removal)",
            )

            for (const authorItem of authorItems) {
                const authorId = authorItem.id
                if (!authorId) {
                    console.error("❌ Author item missing ID")
                    return
                }

                const nameInput = authorItem.querySelector(".author-name-input")
                const orcidInput = authorItem.querySelector(
                    ".author-orcid-input",
                )

                currentAuthors.push({
                    name: nameInput?.value || "",
                    orcid_id: orcidInput?.value || "",
                    _stableId: authorId,
                })
            }
        }

        return currentAuthors
    }
}

if (typeof window !== "undefined") {
    window.AuthorsManager = AuthorsManager
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { AuthorsManager }
}
