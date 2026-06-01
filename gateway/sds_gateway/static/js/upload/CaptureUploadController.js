/**
 * Capture folder upload modal: duplicate check, chunked upload, results.
 */
class CaptureUploadController extends ModalManager {
    constructor(options = {}) {
        super()
        this.options = options

        this.isProcessing = false
        this.uploadInProgress = false
        this.cancelRequested = false
        this.currentAbortController = null

        this.uploadModal = null
        this.cancelButton = null
        this.closeButton = null
        this.submitButton = null
        this.fileInput = null

        this._beforeUnloadHandler = null
        this._visibilityHandler = null

        this.selectedFiles = []
        this.filesToSkip = null
        this.fileCheckResults = null
        this._fileInputChangeHandler = null
    }

    init() {
        this.uploadModal = document.getElementById(
            this.options.uploadModalId || "uploadCaptureModal",
        )
        if (!this.uploadModal) {
            console.warn("uploadCaptureModal not found")
            return
        }

        this.cancelButton =
            this.uploadModal.querySelector(this.options.cancelButtonSelector) ||
            this.uploadModal.querySelector(".btn-secondary")
        this.closeButton =
            this.uploadModal.querySelector(this.options.closeButtonSelector) ||
            this.uploadModal.querySelector(".btn-close")
        this.submitButton = document.getElementById(
            this.options.submitButtonId || "uploadSubmitBtn",
        )
        this.fileInput = document.getElementById(
            this.options.fileInputId || "captureFileInput",
        )

        if (!this.cancelButton || !this.closeButton || !this.submitButton) {
            console.warn("Required buttons not found in upload modal")
            return
        }

        this.clearExistingResultModal()
        this.clearUploadSessionStorage()
        this.addBeforeUnloadGuard()
        this.addVisibilityListener()
        this.addModalStateResetHandlers()
        this.addCancelHandlers()
        this.addSubmitHandler()
        this.wireFileInputSelection()
    }

    clearExistingResultModal() {
        const resultModalId = "uploadResultModal"
        const existingResultModal = document.getElementById(resultModalId)
        if (!existingResultModal) return
        this.closeModal(resultModalId)
    }

    clearUploadSessionStorage() {
        try {
            if (sessionStorage.getItem("uploadInProgress")) {
                sessionStorage.removeItem("uploadInProgress")
            }
        } catch (_) {}
    }

    addBeforeUnloadGuard() {
        if (this._beforeUnloadHandler) {
            window.removeEventListener(
                "beforeunload",
                this._beforeUnloadHandler,
            )
        }
        this._beforeUnloadHandler = (e) => {
            let inProgress = false
            try {
                inProgress =
                    this.isProcessing ||
                    this.uploadInProgress ||
                    Boolean(sessionStorage.getItem("uploadInProgress"))
            } catch (_) {
                inProgress = this.isProcessing || this.uploadInProgress
            }
            if (!inProgress) return
            e.preventDefault()
            e.returnValue =
                "Upload in progress will be aborted. Are you sure you want to leave?"
            return e.returnValue
        }
        window.addEventListener("beforeunload", this._beforeUnloadHandler)
    }

    addVisibilityListener() {
        if (this._visibilityHandler) {
            document.removeEventListener(
                "visibilitychange",
                this._visibilityHandler,
            )
        }
        this._visibilityHandler = () => {
            // Preserve legacy behavior (no-op but keeps a hook if needed later)
            if (
                document.visibilityState === "hidden" &&
                this.uploadInProgress
            ) {
                // page hidden during upload
            }
        }
        document.addEventListener("visibilitychange", this._visibilityHandler)
    }

    addModalStateResetHandlers() {
        this.uploadModal.addEventListener("show.bs.modal", () => {
            this.isProcessing = false
            this.currentAbortController = null
        })
        this.uploadModal.addEventListener("hidden.bs.modal", () => {
            this.isProcessing = false
            this.currentAbortController = null
        })
    }

    wireFileInputSelection() {
        if (!this.fileInput || !this.uploadModal) return

        if (this._fileInputChangeHandler) {
            this.fileInput.removeEventListener(
                "change",
                this._fileInputChangeHandler,
            )
        }
        this._fileInputChangeHandler = (event) => {
            this.isProcessing = false
            this.currentAbortController = null
            const files = event.target.files
            if (!files?.length) return
            this.setSelectedFiles(Array.from(files))
        }
        this.fileInput.addEventListener("change", this._fileInputChangeHandler)
    }

    setSelectedFiles(files) {
        this.selectedFiles = Array.isArray(files) ? files : []
    }

    getSelectedFiles() {
        return this.selectedFiles || []
    }

    resetSession() {
        this.selectedFiles = []
        this.filesToSkip = null
        this.fileCheckResults = null
        this.isProcessing = false
        this.uploadInProgress = false
        this.cancelRequested = false
        this.currentAbortController = null
    }

    addCancelHandlers() {
        this.cancelButton.addEventListener("click", () => {
            this.handleCancellation("cancel")
        })
        this.closeButton.addEventListener("click", () => {
            this.handleCancellation("close")
        })
    }

    addSubmitHandler() {
        const uploadForm = document.getElementById(
            this.options.uploadFormId || "uploadCaptureForm",
        )
        if (!uploadForm) return

        uploadForm.addEventListener("submit", async (e) => {
            e.preventDefault()

            this.isProcessing = true
            this.uploadInProgress = true
            this.cancelRequested = false
            try {
                sessionStorage.setItem("uploadInProgress", "true")
            } catch (_) {}

            try {
                if (!this.selectedFiles || this.selectedFiles.length === 0) {
                    alert("Please select files to upload.")
                    return
                }

                const files = this.selectedFiles

                if (
                    this.checkForLargeFiles(
                        files,
                        this.cancelButton,
                        this.submitButton,
                    )
                ) {
                    return
                }

                await this.checkFilesForDuplicates(files)

                const {
                    filesToUpload,
                    relativePathsToUpload,
                    allRelativePaths,
                    skippedFilesCount,
                } = this.partitionFilesForUpload(files)

                const uploadResults = await this.uploadFilesInChunks(
                    filesToUpload,
                    relativePathsToUpload,
                    allRelativePaths,
                    filesToUpload.length,
                )

                this.currentAbortController = null

                this.showUploadResults(
                    uploadResults,
                    uploadResults.saved_files_count,
                    files.length,
                    skippedFilesCount,
                )
            } catch (error) {
                if (this.cancelRequested) {
                    if (!this.uploadInProgress) {
                        // cancelled during duplicate checking; legacy flow already alerted
                    } else {
                        alert(
                            "Upload cancelled. Any files uploaded before cancellation have been saved.",
                        )
                        setTimeout(() => window.location.reload(), 1000)
                    }
                } else if (error?.name === "AbortError") {
                    alert(
                        "Upload was interrupted. Any files uploaded before the interruption have been saved.",
                    )
                    setTimeout(() => window.location.reload(), 1000)
                } else if (
                    error?.name === "TypeError" &&
                    String(error?.message || "").includes("fetch")
                ) {
                    let shouldSuppress = false
                    try {
                        shouldSuppress =
                            this.uploadInProgress ||
                            Boolean(sessionStorage.getItem("uploadInProgress"))
                    } catch (_) {}
                    if (!shouldSuppress) {
                        alert(
                            "Network error during upload. Please check your connection and try again.",
                        )
                    }
                } else {
                    alert(`Upload failed: ${error?.message || "Unknown error"}`)
                    setTimeout(() => window.location.reload(), 1000)
                }
            } finally {
                this.resetUIState()
            }
        })
    }

    partitionFilesForUpload(files) {
        const filesToUpload = []
        const relativePathsToUpload = []
        const allRelativePaths = []
        let skippedFilesCount = 0

        for (const file of files) {
            const directory = UploadUtils.getDirectoryPathFromFile(file)

            const fileKey = `${directory}/${file.name}`
            const relativePath = file.webkitRelativePath || file.name

            allRelativePaths.push(relativePath)

            if (!this.filesToSkip?.has?.(fileKey)) {
                filesToUpload.push(file)
                relativePathsToUpload.push(relativePath)
            } else {
                skippedFilesCount++
            }
        }

        return {
            filesToUpload,
            relativePathsToUpload,
            allRelativePaths,
            skippedFilesCount,
        }
    }

    /**
     * @param {File[]} files
     * @param {HTMLElement} cancelButton
     * @param {HTMLElement} submitButton
     * @returns {boolean} true if large files blocked flow
     */
    checkForLargeFiles(files, cancelButton, submitButton) {
        const progressSection = document.getElementById(
            "checkingProgressSection",
        )
        const LARGE_FILE_THRESHOLD = 512 * 1024 * 1024 // 512MB
        const largeFiles = (files || []).filter(
            (file) => file && file.size > LARGE_FILE_THRESHOLD,
        )

        if (largeFiles.length === 0) return false

        if (progressSection) progressSection.style.display = "none"
        if (cancelButton) {
            cancelButton.textContent = "Cancel"
            cancelButton.classList.remove("btn-warning")
            cancelButton.disabled = false
        }
        if (submitButton) submitButton.disabled = false

        const largeFileNames = largeFiles.map((file) => file.name).join(", ")
        const alertMessage = `Large files detected (over 512MB): ${largeFileNames}\n\nPlease:\n1. Skip these large files and upload the remaining files, or\n2. Use the SpectrumX SDK (https://pypi.org/project/spectrumx/) to upload large files and add them to your capture.\n\nLarge files may cause issues with the web interface.`
        alert(alertMessage)
        return true
    }

    async checkFilesForDuplicates(files) {
        const progressSection = document.getElementById(
            "checkingProgressSection",
        )
        const progressBar = document.getElementById("checkingProgressBar")
        const progressText = document.getElementById("checkingProgressText")
        const progressMessage = document.getElementById("progressMessage")

        if (progressSection) progressSection.style.display = "block"
        if (progressMessage)
            progressMessage.textContent = "Processing files for upload..."

        if (this.cancelButton)
            this.cancelButton.textContent = "Cancel Processing"
        if (this.submitButton) this.submitButton.disabled = true

        this.filesToSkip = new Set()
        this.fileCheckResults = new Map()

        const csrfToken = window.APIClient.getCSRFToken()
        if (!csrfToken) {
            throw new Error("CSRF token not found")
        }

        const totalFiles = files.length
        const checkFileUrl =
            document.querySelector("[data-check-file-url]")?.dataset
                ?.checkFileUrl || "/users/check-file-exists/"

        for (let i = 0; i < files.length; i++) {
            const file = files[i]

            const progress = Math.round(((i + 1) / totalFiles) * 100)
            if (progressBar) progressBar.style.width = `${progress}%`
            if (progressText) progressText.textContent = `${progress}%`

            const hashHex = await UploadUtils.calculateBlake3Hash(file)
            const directory = UploadUtils.getDirectoryPathFromFile(file)

            try {
                const data = await UploadUtils.checkFileExistsOnServer(
                    file,
                    hashHex,
                    csrfToken,
                    checkFileUrl,
                )

                const fileKey = `${directory}/${file.name}`
                this.fileCheckResults.set(fileKey, {
                    file,
                    directory,
                    filename: file.name,
                    checksum: hashHex,
                    data: data.data,
                })
                if (data?.data?.file_exists_in_tree === true) {
                    this.filesToSkip.add(fileKey)
                }
            } catch (error) {
                console.error("Error checking file:", error)
            }

            if (this.cancelRequested) {
                break
            }
        }

        if (progressSection) progressSection.style.display = "none"

        if (this.cancelRequested) {
            if (progressSection) progressSection.style.display = "none"
            await new Promise((resolve) => setTimeout(resolve, 100))
            alert("Processing cancelled. No files were uploaded.")
            throw new Error("Upload cancelled by user")
        }
    }

    async handleSkippedFilesUpload(allRelativePaths, abortController) {
        const skippedFormData = new FormData()
        for (const path of allRelativePaths) {
            skippedFormData.append("all_relative_paths", path)
        }

        UploadUtils.appendCaptureTypeToFormData(skippedFormData)

        const uploadUrl =
            document.querySelector("[data-upload-url]")?.dataset?.uploadUrl ||
            "/users/upload-capture/"
        const csrfToken = window.APIClient.getCSRFToken()

        const response = await fetch(uploadUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken },
            body: skippedFormData,
            signal: abortController.signal,
        })
        return await response.json()
    }

    calculateTotalChunks(filesToUpload, chunkSizeBytes) {
        return UploadUtils.calculateTotalChunks(filesToUpload, chunkSizeBytes)
    }

    async uploadChunk({
        chunk,
        chunkPaths,
        chunkNum,
        totalChunks,
        filesProcessed,
        isFinalChunk,
        allResults,
        allRelativePaths,
        totalFiles,
        chunkSizeBytes,
    }) {
        const progressBar = document.getElementById("checkingProgressBar")
        const progressText = document.getElementById("checkingProgressText")
        const progressMessage = document.getElementById("progressMessage")

        const progress = Math.round((filesProcessed / totalFiles) * 100)
        if (progressBar) progressBar.style.width = `${progress}%`
        if (progressText) progressText.textContent = `${progress}%`

        if (progressMessage) {
            if (chunk.length === 1 && chunk[0].size > chunkSizeBytes) {
                const file = chunk[0]
                progressMessage.textContent = `Uploading large file: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)...`
            } else {
                progressMessage.textContent = `Uploading chunk ${chunkNum}/${totalChunks} (${filesProcessed} files processed)...`
            }
        }

        const chunkFormData = new FormData()
        for (const file of chunk) chunkFormData.append("files", file)
        for (const path of chunkPaths)
            chunkFormData.append("relative_paths", path)
        for (const path of allRelativePaths)
            chunkFormData.append("all_relative_paths", path)

        UploadUtils.appendCaptureTypeToFormData(chunkFormData)

        chunkFormData.append("is_chunk", "true")
        chunkFormData.append("chunk_number", String(chunkNum))
        chunkFormData.append("total_chunks", String(totalChunks))

        if (this.cancelRequested) {
            throw new Error("Upload cancelled by user")
        }

        const controller = new AbortController()
        this.currentAbortController = controller

        const MIN_AVG_UPLOAD_RATE = 100 * 1024 // 100KB/s
        const MIN_TIMEOUT_MS = 30000
        const totalChunkBytes = chunk.reduce((t, f) => t + f.size, 0)
        const calculatedTimeout = (totalChunkBytes / MIN_AVG_UPLOAD_RATE) * 1000
        const timeout = Math.max(calculatedTimeout, MIN_TIMEOUT_MS)
        const timeoutId = setTimeout(() => controller.abort(), timeout)

        const uploadUrl =
            document.querySelector("[data-upload-url]")?.dataset?.uploadUrl ||
            "/users/upload-capture/"
        const csrfToken = window.APIClient.getCSRFToken()

        let response
        let chunkResult
        try {
            response = await fetch(uploadUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
                body: chunkFormData,
                signal: controller.signal,
            })
            clearTimeout(timeoutId)
            if (!response.ok) {
                throw new Error(
                    `HTTP ${response.status}: ${response.statusText}`,
                )
            }
            chunkResult = await response.json()
        } catch (error) {
            clearTimeout(timeoutId)
            if (error?.name === "AbortError") {
                throw new Error("Upload timeout - connection may be lost")
            }
            throw error
        }

        if (chunkResult.saved_files_count !== undefined) {
            allResults.saved_files_count += chunkResult.saved_files_count
        }
        if (chunkResult.captures && isFinalChunk) {
            allResults.captures = allResults.captures.concat(
                chunkResult.captures,
            )
        }
        if (chunkResult.message && isFinalChunk) {
            allResults.message = chunkResult.message
        }
        if (chunkResult.errors) {
            allResults.errors = allResults.errors.concat(chunkResult.errors)
        }

        if (chunkResult.file_upload_status === "error") {
            allResults.file_upload_status = "error"
            allResults.message = chunkResult.message || "Upload failed"
            if (progressMessage) {
                progressMessage.textContent =
                    "Upload aborted due to errors. Please check the results."
            }
            throw new Error(`Upload failed: ${chunkResult.message}`)
        }
        if (chunkResult.file_upload_status === "success" && isFinalChunk) {
            allResults.file_upload_status = "success"
        }
    }

    async uploadFilesInChunks(
        filesToUpload,
        relativePathsToUpload,
        allRelativePaths,
        totalFiles,
    ) {
        const progressBar = document.getElementById("checkingProgressBar")
        const progressText = document.getElementById("checkingProgressText")
        const progressMessage = document.getElementById("progressMessage")
        const progressSection = document.getElementById(
            "checkingProgressSection",
        )

        if (filesToUpload.length > 0) {
            if (progressSection) progressSection.style.display = "block"
            if (progressMessage)
                progressMessage.textContent =
                    "Uploading files and creating captures..."
            if (progressBar) progressBar.style.width = "0%"
            if (progressText) progressText.textContent = "0%"
        }

        const abortController = new AbortController()
        this.currentAbortController = abortController

        const CHUNK_SIZE_BYTES = 50 * 1024 * 1024

        let allResults = {
            file_upload_status: "success",
            saved_files_count: 0,
            captures: [],
            errors: [],
            message: "",
        }

        if (filesToUpload.length === 0) {
            allResults = await this.handleSkippedFilesUpload(
                allRelativePaths,
                abortController,
            )
        } else {
            let currentChunk = []
            let currentChunkPaths = []
            let currentChunkSize = 0
            let chunkNumber = 1
            let filesProcessed = 0

            const totalChunks = this.calculateTotalChunks(
                filesToUpload,
                CHUNK_SIZE_BYTES,
            )

            for (let i = 0; i < filesToUpload.length; i++) {
                const file = filesToUpload[i]
                const filePath = relativePathsToUpload[i]

                if (
                    currentChunkSize + file.size > CHUNK_SIZE_BYTES &&
                    currentChunk.length > 0
                ) {
                    await this.uploadChunk({
                        chunk: currentChunk,
                        chunkPaths: currentChunkPaths,
                        chunkNum: chunkNumber,
                        totalChunks,
                        filesProcessed,
                        isFinalChunk: false,
                        allResults,
                        allRelativePaths,
                        totalFiles,
                        chunkSizeBytes: CHUNK_SIZE_BYTES,
                    })
                    currentChunk = []
                    currentChunkPaths = []
                    currentChunkSize = 0
                    chunkNumber++
                }

                currentChunk.push(file)
                currentChunkPaths.push(filePath)
                currentChunkSize += file.size
                filesProcessed++

                if (i === filesToUpload.length - 1) {
                    await this.uploadChunk({
                        chunk: currentChunk,
                        chunkPaths: currentChunkPaths,
                        chunkNum: chunkNumber,
                        totalChunks,
                        filesProcessed,
                        isFinalChunk: true,
                        allResults,
                        allRelativePaths,
                        totalFiles,
                        chunkSizeBytes: CHUNK_SIZE_BYTES,
                    })
                }

                if (this.cancelRequested) break
            }
        }

        if (this.cancelRequested) {
            await new Promise((resolve) => setTimeout(resolve, 100))
            throw new Error("Upload cancelled by user")
        }

        if (allResults.file_upload_status === "error") {
            this.currentAbortController = null
            this.showUploadResults(
                allResults,
                allResults.saved_files_count,
                totalFiles,
            )
            return allResults
        }

        this.currentAbortController = null
        return allResults
    }

    resetUIState() {
        if (this.submitButton) this.submitButton.disabled = false

        const progressSection = document.getElementById(
            "checkingProgressSection",
        )
        if (progressSection) progressSection.style.display = "none"

        if (this.cancelButton) {
            this.cancelButton.textContent = "Cancel"
            this.cancelButton.classList.remove("btn-warning")
            this.cancelButton.disabled = false
        }

        if (this.closeButton) {
            this.closeButton.disabled = false
            this.closeButton.style.opacity = "1"
        }

        const progressBar = document.getElementById("checkingProgressBar")
        const progressText = document.getElementById("checkingProgressText")
        const progressMessage = document.getElementById("progressMessage")
        if (progressBar) progressBar.style.width = "0%"
        if (progressText) progressText.textContent = "0%"
        if (progressMessage) progressMessage.textContent = ""

        this.isProcessing = false
        this.uploadInProgress = false
        this.cancelRequested = false
        try {
            sessionStorage.removeItem("uploadInProgress")
        } catch (_) {}
        this.currentAbortController = null
    }

    /**
     * @param {string} buttonType
     */
    handleCancellation(buttonType) {
        if (!this.isProcessing) return
        this.cancelRequested = true
        if (this.currentAbortController) {
            this.currentAbortController.abort()
        }

        if (buttonType === "cancel") {
            this.cancelButton.textContent = "Cancelling..."
            this.cancelButton.disabled = true
        } else if (buttonType === "close") {
            this.closeButton.disabled = true
            this.closeButton.style.opacity = "0.5"
        }

        const progressMessage = document.getElementById("progressMessage")
        if (progressMessage) {
            progressMessage.textContent = "Cancelling upload..."
        }

        setTimeout(() => {
            if (this.cancelRequested) {
                this.resetUIState()
            }
        }, 500)
    }

    showUploadResults(result, uploadedCount, totalCount, skippedCount = 0) {
        if (!this.uploadInProgress && result?.file_upload_status === "error") {
            this.resetUIState()
            return
        }

        const resultModalId = "uploadResultModal"
        const modalBody = document.getElementById("uploadResultModalBody")
        const resultModalEl = document.getElementById(resultModalId)
        if (!modalBody || !resultModalEl) {
            return
        }

        const uploadCaptureModalId = "uploadCaptureModal"
        const captureModalEl = document.getElementById(uploadCaptureModalId)
        if (captureModalEl) {
            this.closeModal(uploadCaptureModalId)
        }

        let msg = ""
        if (result.file_upload_status === "success") {
            if (uploadedCount === 0 && totalCount > 0) {
                msg = `<b>Upload complete!</b><br />All ${totalCount} files already existed on the server.`
            } else if (skippedCount > 0) {
                msg = `<b>Upload complete!</b><br />Files uploaded: <strong>${uploadedCount}</strong> / ${totalCount}`
                msg += `<br />Files already exist: <strong>${skippedCount}</strong>`
            } else {
                msg = `<b>Upload complete!</b><br />Files uploaded: <strong>${uploadedCount}</strong> / ${totalCount}`
            }

            if (result.captures && result.captures.length > 0) {
                const uuids = result.captures
                    .map((uuid) => `<li>${uuid}</li>`)
                    .join("")
                msg += `<br />Created capture UUID(s):<ul>${uuids}</ul>`
            }

            if (result.errors && result.errors.length > 0) {
                const errs = result.errors.map((e) => `<li>${e}</li>`).join("")
                msg += `<br /><b>Errors:</b><ul>${errs}</ul>`
                msg += "<br /><b>Please check details and upload again.</b>"
            }
        } else {
            msg = "<b>Upload Failed</b><br />"
            if (result.message) {
                msg += `${result.message}<br /><br />`
            }
            msg += "<b>Please check file validity and try again.</b>"
            if (result.errors && result.errors.length > 0) {
                const errs = result.errors.map((e) => `<li>${e}</li>`).join("")
                msg += `<br /><br /><b>Error Details:</b><ul>${errs}</ul>`
            }
        }

        modalBody.innerHTML = msg
        this.openModal(resultModalId)

        if (result.file_upload_status === "success") {
            resultModalEl.addEventListener(
                "hidden.bs.modal",
                () => {
                    window.location.reload()
                },
                { once: true },
            )
        }
    }
}

if (typeof window !== "undefined") {
    window.CaptureUploadController = CaptureUploadController
    window.UploadCaptureModalController = CaptureUploadController
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { CaptureUploadController }
}
