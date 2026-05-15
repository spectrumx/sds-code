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
			return "No authors specified.";
		}

		return authors
			.map((author) =>
				typeof author === "string" ? author : author.name || "Unknown",
			)
			.join(", ");
	}

	/**
	 * @returns {{ name: string, orcid_id: string, _stableId: string }[]}
	 */
	static getCurrentAuthorsWithDOMIds() {
		const authorsList = document.querySelector(".authors-list");
		const currentAuthors = [];

		if (authorsList) {
			const authorItems = authorsList.querySelectorAll(
				".author-item:not(.marked-for-removal)",
			);

			for (const authorItem of authorItems) {
				const authorId = authorItem.id;
				if (!authorId) {
					console.error("❌ Author item missing ID");
					return;
				}

				const nameInput = authorItem.querySelector(".author-name-input");
				const orcidInput = authorItem.querySelector(".author-orcid-input");

				currentAuthors.push({
					name: nameInput?.value || "",
					orcid_id: orcidInput?.value || "",
					_stableId: authorId,
				});
			}
		}

		return currentAuthors;
	}
}

if (typeof window !== "undefined") {
	window.AuthorsManager = AuthorsManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { AuthorsManager };
}
