# Visualizations App

The visualizations app provides signal processing and visualization capabilities for SDS (Spectrum Data System) captures. It currently supports generating waterfall displays from DigitalRF capture data.

## Overview

This Django app handles post-processing of RF capture data to create interactive visualizations. It uses Django-cog pipelines for asynchronous processing and provides both web-based views and REST API endpoints.

## Features

### Supported Visualizations

1. **Waterfall Visualization**
   - Interactive scrolling waterfall display with periodogram
   - Real-time signal analysis
   - Supports DigitalRF capture format
   - Available via web interface and API

2. **Spectrogram Visualization** (Under development)
   - 2D frequency vs. time visualization
   - Configurable FFT parameters, window functions, and colormaps
   - Supports DigitalRF capture format
   - Requires `EXPERIMENTAL_SPECTROGRAM` setting to be enabled

### Processing Types

- **Waterfall**: Converts DigitalRF data to JSON format for web visualization
- **Spectrogram**: Generates PNG images with configurable parameters

## Architecture

### Models

- **`PostProcessedData`**: Central model for storing processed visualization data
    - Tracks processing status (pending, processing, completed, failed)
    - Stores processing parameters and metadata
    - Links to capture data and generated files
    - Supports soft deletion and public/private visibility

### Processing Pipeline

The app uses Django-cog for asynchronous processing with a three-stage pipeline:

1. **Setup Stage**: Validates capture and creates processing records
2. **Waterfall Stage**: Processes waterfall data (independent)
3. **Spectrogram Stage**: Processes spectrogram data (independent)

## Pipeline Setup

The visualizations app includes a management command to automatically set up Django-cog pipelines for processing visualizations.

### Management Command

```bash
python manage.py setup_pipelines
```

#### Command Options

- `--pipeline-type {visualization,all}`: Type of pipeline to set up (default: all) (note: there is currently only 1 pipeline)
- `--strategy {abort-if-exists,skip-if-exists,force,smart-recreate}`: Strategy for handling existing pipelines (default: abort-if-exists)

#### Strategies

1. **abort-if-exists** (default): Warns if pipeline exists and exits
2. **skip-if-exists**: Silently skips if pipeline already exists
3. **force**: Deletes existing pipeline and recreates (loses history)
4. **smart-recreate**: Intelligently handles existing pipelines:
   - If no runs exist: deletes old pipeline and creates new timestamped version
   - If runs exist: disables old pipeline without deleting it and creates new timestamped version

## Deployment

### Development vs Production Defaults

The pipeline setup strategy differs between environments:

- **Development (Local)**: Uses `--strategy=smart-recreate`
    - Automatically updates pipelines during development
    - Preserves existing pipeline history when possible
    - Creates timestamped versions to avoid conflicts

- **Production**: Uses `--strategy=skip-if-exists`
    - Prevents accidental pipeline modifications
    - Requires explicit intervention to update pipelines
    - Safer for production deployments

### Updating Pipelines in Production

To update pipelines in production, you have several options:

#### Option 1: Manual Update (Recommended)

```bash
# Connect to production container
docker exec -it <container_name> bash

# Update pipelines with smart recreate
python manage.py setup_pipelines --strategy=smart-recreate
```

#### Option 2: Force Recreation (Use with caution)

```bash
# Force recreate all pipelines (loses history)
python manage.py setup_pipelines --strategy=force
```

## Development

### Adding New Visualization Types

1. Add new `ProcessingType` enum value
2. Create processing function in `processing/` directory
3. Add cog pipeline stage in `cog_pipelines.py`
4. Update compatibility rules in `config.py`
5. Add API endpoints and web views as needed
