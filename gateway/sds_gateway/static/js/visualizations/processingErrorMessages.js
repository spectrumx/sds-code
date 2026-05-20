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
