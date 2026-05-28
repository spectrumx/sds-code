/**
 * User-facing copy for async visualization job failures (spectrogram, waterfall).
 */

export function extractErrorDetail(traceback) {
	if (!traceback) return "Check your capture data for issues.";

	const tracebackLines = traceback.split("\n").filter((line) => line.trim());
	return tracebackLines.length > 0
		? tracebackLines[tracebackLines.length - 1].trim()
		: "Check your capture data for issues.";
}

/**
 * @returns {{ message: string, errorDetail: string|null }}
 */
/** Extract a readable error detail from API JSON (spectrogram create/status). */
export function extractApiResponseDetail(responseData) {
	if (!responseData) return null;
	if (typeof responseData === "string") return responseData;
	const detailFields = ["detail", "error", "message"];
	for (const fieldName of detailFields) {
		if (typeof responseData[fieldName] === "string") {
			return responseData[fieldName];
		}
	}
	if (Array.isArray(responseData.errors)) {
		return responseData.errors.join(", ");
	}
	if (
		responseData.errors &&
		typeof responseData.errors === "object" &&
		!Array.isArray(responseData.errors)
	) {
		const firstFieldErrors = Object.entries(responseData.errors)[0];
		if (!firstFieldErrors) return null;
		const [fieldName, fieldValue] = firstFieldErrors;
		if (Array.isArray(fieldValue)) {
			return `${fieldName}: ${fieldValue.join(", ")}`;
		}
		if (typeof fieldValue === "string") {
			return `${fieldName}: ${fieldValue}`;
		}
	}
	return null;
}

export function generateErrorMessage(errorInfo, hasSourceDataError) {
	const message = hasSourceDataError
		? "An error occurred while processing; it may be due to an issue with the capture data."
		: "A server error occurred during processing. Please try again.";

	let errorDetail = null;
	if (hasSourceDataError && errorInfo.traceback) {
		errorDetail = extractErrorDetail(errorInfo.traceback);
	}

	return { message, errorDetail };
}
