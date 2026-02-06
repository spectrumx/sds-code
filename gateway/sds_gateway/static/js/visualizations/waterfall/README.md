# Waterfall Visualization

This module renders waterfall (and periodogram) visualizations for SDS captures. It supports two ways of loading slice data: **preprocessed** (from a stored file) and **streaming** (on-demand FFT). The main reason for streaming is to handle **large captures** without loading a full preprocessed file.

---

## Two Modes

### Preprocessed (same as master when not large)

- A post-processing job has already run and stored the full waterfall for the capture.
- When preprocessed exists and the capture is not “large”, we **load the full file** and run **calculatePowerBounds()** over all slices (same as master). Scale and behavior match master exactly.
- **Pros:** Scale matches master (min/max over all data + 5% margin); no approximation.
- **Cons:** Full file download; for very large captures we use streaming instead.

### Streaming (on-demand)

- No preprocessing required. Metadata comes from OpenSearch; slices are computed on demand via `waterfall_slices_stream` (read DRF + FFT per request).
- **Pros:** View immediately; works for very large captures where preprocessing is slow or impractical.
- **Cons:** Scale is from a sample (e.g. 3 slices); each scroll/range does real work on the backend.

---

## How We Decide Which Mode

The decision runs in `WaterfallVisualization.loadWaterfallData()` in this order:

1. **Fetch streaming metadata**  
   `GET .../waterfall_metadata_stream/` (lightweight; no file download).

2. **Large capture → stream**  
   If `metadata.total_slices >= LARGE_CAPTURE_THRESHOLD` (see `constants.js`, default 50,000):
   - Use **streaming** (`tryLoadStreamingMode()`).
   - Return; do not use preprocessed even if it exists.  
   This is the main way we **stream large captures**.

3. **Otherwise check preprocessed**  
   `GET .../post_processing_status/`.  
   If any entry has `processing_type === "waterfall"` and `processing_status === "completed"`:
   - Use **preprocessed** by loading the full file and running `calculatePowerBounds()` (`loadFullPreprocessedDataLikeMaster()`). Same as master.
   - Return.

4. **No preprocessed → try streaming**  
   Call `tryLoadStreamingMode()`. If it succeeds (e.g. DRF capture), use streaming.

5. **Fallback**  
   If streaming is not available (e.g. not a Digital RF capture), call `loadPreprocessedData()` (slice-on-demand or trigger processing).

So: **large captures always prefer streaming**; smaller captures use preprocessed when available, otherwise streaming.

---

## Color Scale (Power Bounds)

- **Preprocessed (full-file path):** Scale is **calculatePowerBounds()** over all parsed slices (min/max + 5% margin). Same as master; no approximation.
- **Streaming:** Scale from stored `get_post_processed_metadata` when available; else backend sample (7 slices) or client `calculatePowerBoundsFromSamples()` (3 slices).

Constants for default scale live in `constants.js` (e.g. `DEFAULT_SCALE_MIN`, `DEFAULT_SCALE_MAX`).

---

## Key Files

| File | Role |
|------|------|
| `WaterfallVisualization.js` | Orchestrator: load decision, scale, render, preprocessed vs streaming flow. |
| `WaterfallSliceLoader.js` | Fetches slice ranges (preprocessed or streaming endpoint), batching, retries. |
| `WaterfallSliceCache.js` | In-memory cache of slices (LRU); used in both modes for the visible window. |
| `WaterfallRenderer.js` | Canvas drawing, color map, scale bounds. |
| `WaterfallControls.js` | Slice/window controls. |
| `PeriodogramChart.js` | Periodogram chart for the selected slice. |
| `constants.js` | Thresholds, window size, cache size, API endpoints. |

---

## Backend Endpoints

- `GET .../post_processing_status/` — List of post-processed data (type, status). Used to see if a completed waterfall exists.
- `GET .../waterfall_metadata_stream/` — Streaming metadata (e.g. `total_slices`, frequency bounds). No preprocessing; used for size check and streaming init.
- `GET .../waterfall_slices_stream/?start_index=&end_index=` — On-demand slice range (DRF read + FFT). Used in streaming mode.
- `GET .../waterfall_slices/?start_index=&end_index=&processing_type=waterfall` — Slice range from stored preprocessed file. Used in preprocessed mode.
- `GET .../get_post_processed_metadata/?processing_type=waterfall` — Stored metadata (e.g. `power_bounds`) for a completed preprocessed waterfall.

---

## Constants (constants.js)

- **LARGE_CAPTURE_THRESHOLD** (default 50,000) — Above this many slices we prefer streaming. Tune this to change what counts as “large.”
- **WATERFALL_WINDOW_SIZE** (100) — Number of slices drawn in the visible waterfall window.
- **CACHE_SIZE** (800) — Max cached slices for scrolling.
- **BATCH_SIZE** (100) — Slices per API request (should match backend `MAX_SLICE_BATCH_SIZE` where applicable).
- **PREFETCH_DISTANCE** — Slices to load ahead of the current window for smoother scrolling.

---

## Debugging

Use the Network tab to confirm which path runs: `waterfall_metadata_stream` (then streaming vs full download), `download_post_processed_data` (full preprocessed load like master), or `waterfall_slices_stream` (streaming slices). `console.warn` is used for streaming/preprocessed failures.
