/**
 * Shared capture upload FormData helpers and byte-based chunk counting.
 * Used by FilesUploadModal and UploadCaptureModalController.
 */
class ChunkUploadPipeline {
	/**
	 * Append capture type + related fields from the upload modal DOM.
	 * @param {FormData} formData
	 */
	static appendCaptureTypeToFormData(formData) {
		const captureType =
			document.getElementById("captureTypeSelect")?.value || "";
		formData.append("capture_type", captureType);

		if (captureType === "drf") {
			formData.append(
				"channels",
				document.getElementById("captureChannelsInput")?.value || "",
			);
		} else if (captureType === "rh") {
			formData.append(
				"scan_group",
				document.getElementById("captureScanGroupInput")?.value || "",
			);
		}
	}

	/**
	 * Count POST chunks when grouping files by total byte size per chunk.
	 * @param {File[]} filesToUpload
	 * @param {number} chunkSizeBytes
	 * @returns {number}
	 */
	static calculateTotalChunks(filesToUpload, chunkSizeBytes) {
		let totalChunks = 0;
		let tempChunkSize = 0;
		let tempChunkFiles = 0;

		for (const file of filesToUpload) {
			if (tempChunkSize + file.size > chunkSizeBytes && tempChunkFiles > 0) {
				totalChunks++;
				tempChunkSize = 0;
				tempChunkFiles = 0;
			}

			if (file.size > chunkSizeBytes) {
				totalChunks++;
				tempChunkSize = 0;
				tempChunkFiles = 0;
			} else {
				tempChunkSize += file.size;
				tempChunkFiles++;
			}
		}

		if (tempChunkSize > 0) totalChunks++;
		return totalChunks;
	}
}

if (typeof window !== "undefined") {
	window.ChunkUploadPipeline = ChunkUploadPipeline;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { ChunkUploadPipeline };
}
