/**
 * Pagination controls.
 * Migrated from deprecated/components.js.
 */

class PaginationManager {
	constructor(config) {
		this.containerId = config.containerId;
		this.container = document.getElementById(this.containerId);
		this.onPageChange = config.onPageChange;
	}

	update(pagination) {
		if (!this.container || !pagination) return;

		this.container.innerHTML = "";

		if (pagination.num_pages <= 1) return;

		const ul = document.createElement("ul");
		ul.className = "pagination justify-content-center";

		// Previous button
		if (pagination.has_previous) {
			ul.innerHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.number - 1}" aria-label="Previous">
                        <span aria-hidden="true">&laquo;</span>
                    </a>
                </li>
            `;
		}

		// Page numbers
		const startPage = Math.max(1, pagination.number - 2);
		const endPage = Math.min(pagination.num_pages, pagination.number + 2);

		for (let i = startPage; i <= endPage; i++) {
			ul.innerHTML += `
                <li class="page-item ${i === pagination.number ? "active" : ""}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
		}

		// Next button
		if (pagination.has_next) {
			ul.innerHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.number + 1}" aria-label="Next">
                        <span aria-hidden="true">&raquo;</span>
                    </a>
                </li>
            `;
		}

		this.container.appendChild(ul);

		// Add click handlers
		const links = ul.querySelectorAll("a.page-link");
		for (const link of links) {
			link.addEventListener("click", (e) => {
				e.preventDefault();
				const page = Number.parseInt(e.target.dataset.page);
				if (page && this.onPageChange) {
					this.onPageChange(page);
				}
			});
		}
	}

if (typeof window !== "undefined") {
	window.PaginationManager = PaginationManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { PaginationManager };
}

