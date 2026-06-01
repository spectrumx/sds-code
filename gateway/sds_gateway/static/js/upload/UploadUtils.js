/**
 * Stateless helpers for capture / file uploads (hash, chunks, DataTransfer walk, FormData).
 */
const UploadUtils = {
    getCheckFileExistsUrl() {
        return (
            window.checkFileExistsUrl ||
            document.querySelector("[data-check-file-url]")?.dataset
                ?.checkFileUrl ||
            "/users/check-file-exists/"
        )
    },

    getUploadPostUrl() {
        return (
            window.uploadFilesUrl ||
            document.querySelector("[data-upload-url]")?.dataset?.uploadUrl ||
            "/users/upload-capture/"
        )
    },

    getDirectoryPathFromFile(file) {
        if (!file?.webkitRelativePath) return "/"
        const pathParts = file.webkitRelativePath.split("/")
        if (pathParts.length > 1) {
            pathParts.pop()
            return `/${pathParts.join("/")}`
        }
        return "/"
    },

    async calculateBlake3Hash(file) {
        if (typeof hashwasm === "undefined" || !hashwasm?.createBLAKE3) {
            throw new Error("BLAKE3 library not loaded")
        }
        const buffer = await file.arrayBuffer()
        const hasher = await hashwasm.createBLAKE3()
        hasher.init()
        hasher.update(new Uint8Array(buffer))
        return hasher.digest("hex")
    },

    async checkFileExistsOnServer(file, hashHex, csrfToken, url) {
        const directory = UploadUtils.getDirectoryPathFromFile(file)
        const response = await fetch(
            url || UploadUtils.getCheckFileExistsUrl(),
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken":
                        csrfToken || window.APIClient?.getCSRFToken?.() || "",
                },
                body: JSON.stringify({
                    directory,
                    filename: file.name,
                    checksum: hashHex,
                }),
            },
        )
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        return response.json()
    },

    appendCaptureTypeToFormData(formData) {
        const captureType =
            document.getElementById("captureTypeSelect")?.value || ""
        formData.append("capture_type", captureType)
        if (captureType === "drf") {
            formData.append(
                "channels",
                document.getElementById("captureChannelsInput")?.value || "",
            )
        } else if (captureType === "rh") {
            formData.append(
                "scan_group",
                document.getElementById("captureScanGroupInput")?.value || "",
            )
        }
    },

    calculateTotalChunks(filesToUpload, chunkSizeBytes) {
        let totalChunks = 0
        let tempChunkSize = 0
        let tempChunkFiles = 0
        for (const file of filesToUpload) {
            if (
                tempChunkSize + file.size > chunkSizeBytes &&
                tempChunkFiles > 0
            ) {
                totalChunks++
                tempChunkSize = 0
                tempChunkFiles = 0
            }
            if (file.size > chunkSizeBytes) {
                totalChunks++
                tempChunkSize = 0
                tempChunkFiles = 0
            } else {
                tempChunkSize += file.size
                tempChunkFiles++
            }
        }
        if (tempChunkSize > 0) totalChunks++
        return totalChunks
    },

    convertToFiles(itemsOrFiles) {
        if (!itemsOrFiles) return []
        const first = itemsOrFiles[0]
        if (first && typeof first.getAsFile === "function") {
            return Array.from(itemsOrFiles)
                .map((item) => item.getAsFile())
                .filter((f) => !!f)
        }
        return Array.from(itemsOrFiles)
    },

    async collectFilesFromDataTransfer(dataTransfer) {
        const items = Array.from(dataTransfer.items || [])
        const supportsEntries =
            items.length > 0 && typeof items[0].webkitGetAsEntry === "function"
        if (!supportsEntries) {
            return UploadUtils.convertToFiles(
                dataTransfer.files?.length
                    ? dataTransfer.files
                    : dataTransfer.items,
            )
        }
        const allFiles = []
        for (const item of items) {
            if (item.kind !== "file") continue
            const entry = item.webkitGetAsEntry()
            if (!entry) continue
            const files = await UploadUtils.traverseEntry(entry)
            allFiles.push(...files)
        }
        return allFiles
    },

    async traverseEntry(entry) {
        if (entry.isFile) {
            return new Promise((resolve) => {
                entry.file((file) => {
                    try {
                        const relative = (entry.fullPath || file.name).replace(
                            /^\//,
                            "",
                        )
                        Object.defineProperty(file, "webkitRelativePath", {
                            value: relative,
                            configurable: true,
                        })
                    } catch (_) {}
                    resolve([file])
                })
            })
        }
        if (entry.isDirectory) {
            const reader = entry.createReader()
            const entries = await UploadUtils.readAllEntries(reader)
            const nestedFiles = []
            for (const child of entries) {
                const files = await UploadUtils.traverseEntry(child)
                nestedFiles.push(...files)
            }
            return nestedFiles
        }
        return []
    },

    readAllEntries(reader) {
        return new Promise((resolve) => {
            const entries = []
            const readChunk = () => {
                reader.readEntries((results) => {
                    if (!results.length) {
                        resolve(entries)
                        return
                    }
                    entries.push(...results)
                    readChunk()
                })
            }
            readChunk()
        })
    },
}

if (typeof window !== "undefined") {
    window.UploadUtils = UploadUtils
    // Back-compat for any stray references during transition
    window.ChunkUploadPipeline = UploadUtils
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { UploadUtils }
}
