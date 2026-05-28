/**
 * Binds create/edit dataset author list UI (shared DOM + server render).
 */
class DatasetAuthorsUI {
	static PRIMARY_AUTHOR_WARNING =
		"The primary author cannot be removed. This is the dataset creator.";

	/**
	 * @param {DatasetCreationHandler|DatasetEditingHandler} handler
	 * @param {{ mode: 'create'|'edit', initialAuthors?: unknown[] }} options
	 */
	static mount(handler, options) {
		if (options.mode === "edit") {
			this._mountEdit(handler, options);
		} else {
			this._mountCreate(handler);
		}
	}

	static _getDom() {
		const authorsContainer = document.getElementById("authors-container");
		const authorsList = authorsContainer?.querySelector(".authors-list");
		const addAuthorBtn = document.getElementById("add-author-btn");
		const authorsHiddenField = document.getElementById("id_authors");
		if (!authorsContainer || !authorsList || !authorsHiddenField) {
			return null;
		}
		return { authorsList, addAuthorBtn, authorsHiddenField };
	}

	static _mountCreate(handler) {
		const dom = this._getDom();
		if (!dom) return;

		const utils = window.AuthorsManager;
		const { authorsList, addAuthorBtn, authorsHiddenField } = dom;

		let authors = utils.parseAuthorsFromHiddenField(authorsHiddenField.value);
		authors = utils.normalizeAuthorEntries(authors);
		authors = utils.ensureDefaultAuthorIfEmpty(authors);

		const updateAuthorsDisplay = async () => {
			await utils.refreshAuthorsList(handler, {
				authorsList,
				authorsHiddenField,
				authors,
				addAuthorBtn,
				addButtonMode: "always",
			});
		};

		const addAuthor = () => {
			authors.push({ name: "", orcid_id: "" });
			updateAuthorsDisplay();
			utils.focusAuthorNameInput(authorsList, authors.length - 1);
			handler.validateCurrentStep?.();
			utils.notifyReviewDisplay();
		};

		const removeAuthor = (index) => {
			if (index > 0) {
				authors.splice(index, 1);
				updateAuthorsDisplay();
				handler.validateCurrentStep?.();
				utils.notifyReviewDisplay();
			} else {
				handler.showToast(this.PRIMARY_AUTHOR_WARNING, "warning");
			}
		};

		if (addAuthorBtn) {
			addAuthorBtn.addEventListener("click", addAuthor);
		}

		authorsList.addEventListener("input", (e) => {
			if (
				!e.target.classList.contains("author-name-input") &&
				!e.target.classList.contains("author-orcid-input")
			) {
				return;
			}
			const index = Number.parseInt(e.target.dataset.index);
			const field = e.target.dataset.field;
			utils.ensureAuthorRecord(authors, index);
			authors[index][field] = e.target.value;
			const needsUpdate = utils.removeTrailingEmptyAuthor(authors, index);
			authorsHiddenField.value = JSON.stringify(authors);
			if (needsUpdate) {
				updateAuthorsDisplay();
			}
			handler.validateCurrentStep?.();
			utils.notifyReviewDisplay();
		});

		authorsList.addEventListener("click", (e) => {
			const removeButton = e.target.closest(".remove-author");
			if (!removeButton) return;
			e.preventDefault();
			e.stopPropagation();
			removeAuthor(Number.parseInt(removeButton.dataset.index));
		});

		updateAuthorsDisplay();
		handler.authors = authors;
		handler.updateAuthorsDisplay = updateAuthorsDisplay;

		window.updateDatasetAuthors = (authorsField) =>
			handler.updateDatasetAuthors(authorsField);
		window.formatAuthors = (authors) => handler.formatAuthors(authors);
	}

	static _mountEdit(handler, options) {
		window.updateDatasetAuthors = (authorsField) =>
			handler.updateDatasetAuthors(authorsField);
		window.formatAuthors = (authors) => handler.formatAuthors(authors);

		const dom = this._getDom();
		if (!dom) return;

		const utils = window.AuthorsManager;
		const { authorsList, addAuthorBtn, authorsHiddenField } = dom;

		let authors = utils.parseAuthorsFromHiddenField(authorsHiddenField.value);
		authors = utils.normalizeAuthorEntries(authors);

		const datasetAuthors = options.initialAuthors || [];
		let originalAuthors = Array.isArray(datasetAuthors) ? datasetAuthors : [];
		originalAuthors = utils.normalizeAuthorEntries(originalAuthors);

		const authorChanges = utils.detectInitialAuthorChanges(
			authors,
			originalAuthors,
		);

		const updateAuthorsDisplay = async () => {
			await utils.refreshAuthorsList(handler, {
				authorsList,
				authorsHiddenField,
				authors,
				addAuthorBtn,
				removedIndices: authorChanges.removed,
				addButtonMode: "permission",
			});
		};

		const addAuthor = () => {
			const newIndex = authors.length;
			authors.push({ name: "", orcid_id: "" });
			if (!authorChanges.added.includes(newIndex)) {
				authorChanges.added.push(newIndex);
			}
			updateAuthorsDisplay();
			utils.focusAuthorNameInput(authorsList, newIndex);
			utils.notifyReviewDisplay();
		};

		const removeAuthor = (index) => {
			if (index <= 0) {
				handler.showToast(this.PRIMARY_AUTHOR_WARNING, "warning");
				return;
			}
			const isNewlyAdded = authorChanges.added.includes(index);
			if (isNewlyAdded) {
				authors.splice(index, 1);
				const addIndex = authorChanges.added.indexOf(index);
				if (addIndex > -1) {
					authorChanges.added.splice(addIndex, 1);
				}
				authorChanges.added = authorChanges.added.map((i) =>
					i > index ? i - 1 : i,
				);
				authorChanges.removed = authorChanges.removed.map((i) =>
					i > index ? i - 1 : i,
				);
				const newModified = {};
				for (const [modifiedIndex, changes] of Object.entries(
					authorChanges.modified,
				)) {
					const numIndex = Number.parseInt(modifiedIndex);
					if (numIndex > index) {
						newModified[numIndex - 1] = changes;
					} else if (numIndex < index) {
						newModified[numIndex] = changes;
					}
				}
				authorChanges.modified = newModified;
			} else if (!authorChanges.removed.includes(index)) {
				authorChanges.removed.push(index);
			}
			updateAuthorsDisplay();
			utils.notifyReviewDisplay();
		};

		const cancelAuthorRemoval = (index) => {
			if (!authorChanges.removed.includes(index)) return;
			const removeIndex = authorChanges.removed.indexOf(index);
			if (removeIndex > -1) {
				authorChanges.removed.splice(removeIndex, 1);
			}
			updateAuthorsDisplay();
			utils.notifyReviewDisplay();
		};

		if (addAuthorBtn) {
			addAuthorBtn.addEventListener("click", addAuthor);
		}

		authorsList.addEventListener("input", (e) => {
			if (
				!e.target.classList.contains("author-name-input") &&
				!e.target.classList.contains("author-orcid-input")
			) {
				return;
			}
			const index = Number.parseInt(e.target.dataset.index);
			const field = e.target.dataset.field;
			utils.ensureAuthorRecord(authors, index);
			authors[index][field] = e.target.value;

			if (index < originalAuthors.length) {
				const originalAuthor = originalAuthors[index];
				const originalValue =
					typeof originalAuthor === "string"
						? field === "name"
							? originalAuthor
							: ""
						: originalAuthor[field] || "";

				if (e.target.value !== originalValue) {
					if (!authorChanges.modified[index]) {
						authorChanges.modified[index] = {};
					}
					authorChanges.modified[index][field] = {
						old: originalValue,
						new: e.target.value,
					};
				} else if (authorChanges.modified[index]) {
					delete authorChanges.modified[index][field];
					if (Object.keys(authorChanges.modified[index]).length === 0) {
						delete authorChanges.modified[index];
					}
				}
			}

			const needsUpdate = utils.removeTrailingEmptyAuthor(authors, index);
			authorsHiddenField.value = JSON.stringify(authors);
			if (needsUpdate) {
				updateAuthorsDisplay();
			}
			utils.notifyReviewDisplay();
		});

		authorsList.addEventListener("click", (e) => {
			const removeButton = e.target.closest(".remove-author");
			const cancelButton = e.target.closest(".cancel-remove-author");
			if (removeButton) {
				e.preventDefault();
				e.stopPropagation();
				removeAuthor(Number.parseInt(removeButton.dataset.index));
			} else if (cancelButton) {
				e.preventDefault();
				e.stopPropagation();
				cancelAuthorRemoval(Number.parseInt(cancelButton.dataset.index));
			}
		});

		updateAuthorsDisplay();
		handler.authors = authors;
		handler.originalAuthors = originalAuthors;
		handler.authorChanges = authorChanges;
		handler.updateAuthorsDisplay = updateAuthorsDisplay;

		window.getAuthorChanges = () => authorChanges;
		window.calculateAuthorChanges = (orig, current) =>
			handler.calculateAuthorChanges(orig, current);
		window.getCurrentAuthorsWithDOMIds = () =>
			handler.getCurrentAuthorsWithDOMIds();
		window.captureAuthorsWithDOMIds = (a) => handler.captureAuthorsWithDOMIds(a);

		window.cancelAuthorAddition = (index) => {
			if (!authorChanges.added.includes(index)) return;
			const removeIndex = authorChanges.added.indexOf(index);
			if (removeIndex > -1) {
				authorChanges.added.splice(removeIndex, 1);
			}
			authors.splice(index, 1);
			updateAuthorsDisplay();
			utils.notifyReviewDisplay();
		};

		window.cancelAuthorRemoval = (index) => {
			cancelAuthorRemoval(index);
		};

		window.cancelAuthorModification = (index, field) => {
			if (!authorChanges.modified[index]?.[field]) return;
			delete authorChanges.modified[index][field];
			if (Object.keys(authorChanges.modified[index]).length === 0) {
				delete authorChanges.modified[index];
			}
			if (originalAuthors[index]) {
				const originalAuthor = originalAuthors[index];
				const originalValue =
					typeof originalAuthor === "string"
						? field === "name"
							? originalAuthor
							: ""
						: originalAuthor[field] || "";
				authors[index][field] = originalValue;
			}
			updateAuthorsDisplay();
			utils.notifyReviewDisplay();
		};
	}
}

window.DatasetAuthorsUI = DatasetAuthorsUI;

if (typeof module !== "undefined" && module.exports) {
	module.exports = { DatasetAuthorsUI };
}
