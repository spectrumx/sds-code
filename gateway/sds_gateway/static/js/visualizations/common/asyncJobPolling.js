/**
 * Shared interval polling helpers for async visualization jobs.
 * @param {{ pollingInterval?: ReturnType<typeof setInterval> | null }} host
 * @param {() => void | Promise<void>} tick
 * @param {number} [intervalMs]
 */
export function startAsyncJobPolling(host, tick, intervalMs = 3000) {
    if (host.pollingInterval) {
        clearInterval(host.pollingInterval)
    }
    host.pollingInterval = setInterval(() => {
        void tick()
    }, intervalMs)
}

/**
 * @param {{ pollingInterval?: ReturnType<typeof setInterval> | null }} host
 */
export function stopAsyncJobPolling(host) {
    if (host.pollingInterval) {
        clearInterval(host.pollingInterval)
        host.pollingInterval = null
    }
}
