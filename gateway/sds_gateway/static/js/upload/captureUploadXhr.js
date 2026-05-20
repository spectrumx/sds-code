/**
 * XHR upload for capture file FormData (progress UI hooks).
 * @param {FormData} formData
 * @param {string} csrfToken
 * @param {object} [progressEls] - { wrap, bar, text } element ids or elements
 * @returns {Promise<{ ok: boolean, status: number, headers: Headers, json: Function, text: Function }>}
 */
function postCaptureUploadFormData(formData, csrfToken, progressEls = {}) {
	const wrap =
		typeof progressEls.wrap === "string"
			? document.getElementById(progressEls.wrap)
			: progressEls.wrap;
	const bar =
		typeof progressEls.bar === "string"
			? document.getElementById(progressEls.bar)
			: progressEls.bar;
	const text =
		typeof progressEls.text === "string"
			? document.getElementById(progressEls.text)
			: progressEls.text;

	return new Promise((resolve, reject) => {
		const xhr = new XMLHttpRequest();
		xhr.open("POST", "/users/upload-files/");
		xhr.withCredentials = true;
		xhr.setRequestHeader("X-CSRFToken", csrfToken);
		xhr.setRequestHeader("Accept", "application/json");

		if (wrap) wrap.classList.remove("d-none");
		const setBarIndeterminate = () => {
			if (!bar) return;
			bar.classList.add("progress-bar-striped", "progress-bar-animated");
			bar.style.width = "100%";
			bar.setAttribute("aria-valuenow", "100");
			bar.textContent = "";
		};
		setBarIndeterminate();
		if (text) text.textContent = "Uploading…";

		xhr.upload.onprogress = () => {
			if (text) text.textContent = "Uploading…";
		};
		xhr.onerror = () => reject(new Error("Network error during upload"));
		xhr.upload.onloadstart = () => {
			if (text) text.textContent = "Starting upload…";
		};
		xhr.upload.onloadend = () => {
			setBarIndeterminate();
			if (text) text.textContent = "Processing on server…";
		};
		xhr.onload = () => {
			const status = xhr.status;
			const headers = new Headers({
				"content-type": xhr.getResponseHeader("content-type") || "",
			});
			const bodyText = xhr.responseText || "";
			resolve({
				ok: status >= 200 && status < 300,
				status,
				headers,
				json: async () => {
					try {
						return JSON.parse(bodyText);
					} catch {
						return {};
					}
				},
				text: async () => bodyText,
			});
		};
		xhr.send(formData);
	});
}

if (typeof window !== "undefined") {
	window.postCaptureUploadFormData = postCaptureUploadFormData;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { postCaptureUploadFormData };
}
