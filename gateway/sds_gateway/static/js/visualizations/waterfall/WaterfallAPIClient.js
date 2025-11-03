/**
 * Waterfall API Client
 * Handles all API requests for waterfall visualization
 */

class WaterfallAPIClient {
	constructor(captureUuid) {
		this.captureUuid = captureUuid;
	}

	/**
	 * Get CSRF token from form input
	 */
	getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Get create waterfall endpoint URL
	 */
	_getCreateWaterfallEndpoint() {
		return `/api/v1/visualizations/${this.captureUuid}/create_waterfall/`;
	}

	/**
	 * Get waterfall status endpoint URL
	 */
	_getWaterfallStatusEndpoint(jobId) {
		return `/api/v1/visualizations/${this.captureUuid}/waterfall_status/?job_id=${jobId}`;
	}

	/**
	 * Get waterfall metadata endpoint URL
	 */
	_getWaterfallMetadataEndpoint(jobId) {
		return `/api/v1/visualizations/${this.captureUuid}/waterfall_metadata/?job_id=${jobId}`;
	}

	/**
	 * Get waterfall result endpoint URL
	 */
	_getWaterfallResultEndpoint(jobId, startIndex = null, endIndex = null) {
		let url = `/api/v1/visualizations/${this.captureUuid}/download_waterfall/?job_id=${jobId}`;
		const params = new URLSearchParams();
		if (startIndex !== null) {
			params.append("start_index", startIndex);
		}
		if (endIndex !== null) {
			params.append("end_index", endIndex);
		}
		const queryString = params.toString();
		if (queryString) {
			url += `&${queryString}`;
		}
		return url;
	}

	/**
	 * Get post-processing status for a capture
	 */
	async getPostProcessingStatus() {
		const response = await fetch(
			`/api/latest/assets/captures/${this.captureUuid}/post_processing_status/`,
		);

		if (!response.ok) {
			throw new Error(
				`Failed to get post-processing status: ${response.status}`,
			);
		}

		return await response.json();
	}

	/**
	 * Get waterfall metadata
	 */
	async getWaterfallMetadata(jobId) {
		const response = await fetch(this._getWaterfallMetadataEndpoint(jobId), {
			headers: {
				"X-CSRFToken": this.getCSRFToken(),
			},
		});

		if (!response.ok) {
			throw new Error(`Failed to load waterfall metadata: ${response.status}`);
		}

		return await response.json();
	}

	/**
	 * Load a range of waterfall slices
	 */
	async loadWaterfallRange(jobId, startIndex, endIndex) {
		const response = await fetch(
			this._getWaterfallResultEndpoint(jobId, startIndex, endIndex),
			{
				headers: {
					"X-CSRFToken": this.getCSRFToken(),
				},
			},
		);

		if (!response.ok) {
			throw new Error(`Failed to load waterfall range: ${response.status}`);
		}

		const result = await response.json();
		return result.data || [];
	}

	/**
	 * Create a waterfall processing job
	 */
	async createWaterfallJob() {
		const response = await fetch(this._getCreateWaterfallEndpoint(), {
			method: "POST",
			headers: {
				"X-CSRFToken": this.getCSRFToken(),
			},
		});

		if (!response.ok) {
			throw new Error(`HTTP ${response.status}: ${response.statusText}`);
		}

		const data = await response.json();

		if (!data.uuid) {
			throw new Error("Waterfall job ID not found");
		}

		return data;
	}

	/**
	 * Get waterfall job status
	 */
	async getWaterfallJobStatus(jobId) {
		const response = await fetch(this._getWaterfallStatusEndpoint(jobId), {
			headers: {
				"X-CSRFToken": this.getCSRFToken(),
			},
		});

		if (!response.ok) {
			throw new Error(`HTTP ${response.status}: ${response.statusText}`);
		}

		return await response.json();
	}
}

export { WaterfallAPIClient };
