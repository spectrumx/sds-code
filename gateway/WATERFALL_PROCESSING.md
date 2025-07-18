# Waterfall Processing Implementation

This document describes the implementation of post-processing functionality for creating waterfall visualizations from DigitalRF captures in the SDS Gateway.

## Overview

The waterfall processing system automatically converts DigitalRF captures into waterfall visualization data that can be used by the SVI (SpectrumX Visualization Interface) or other visualization tools. The system runs as a background task using Celery and stores the processed data in the SDS database.

## Architecture

### Components

1. **WaterfallData Model** (`sds_gateway/api_methods/models.py`)
   - Stores processed waterfall data and metadata
   - Tracks processing status and errors
   - Links to the original capture

2. **Processing Task** (`sds_gateway/api_methods/tasks.py`)
   - `process_capture_waterfall()`: Main Celery task
   - Downloads DigitalRF files from SDS storage
   - Converts data to waterfall format using FFT processing
   - Stores results back to SDS

3. **API Endpoints** (`sds_gateway/api_methods/views/capture_endpoints.py`)
   - `POST /api/captures/{uuid}/process_waterfall/`: Manually trigger processing
   - `GET /api/captures/{uuid}/waterfall_status/`: Check processing status
   - Waterfall data included in capture GET responses

4. **Django Signal** (`sds_gateway/api_methods/models.py`)
   - Automatically triggers processing when new DigitalRF captures are created

## Data Flow

1. **Capture Creation**: When a new DigitalRF capture is created, a Django signal triggers the waterfall processing task
2. **File Download**: The task downloads DigitalRF files from MinIO storage
3. **Data Processing**: DigitalRF data is processed using FFT to create waterfall slices
4. **Storage**: Processed data is stored as HDF5 files in SDS storage
5. **Metadata Update**: Processing status and metadata are updated in the database

## Processing Parameters

- **FFT Size**: 1024 (default, configurable)
- **Samples per Slice**: 1024 (default, configurable)
- **Output Format**: HDF5 with compressed datasets
- **Data Type**: 32-bit float (dB values)

## API Usage

### Automatic Processing

Waterfall processing is automatically triggered when a new DigitalRF capture is created via the API or web UI.

### Manual Processing

To manually trigger processing for an existing capture:

```bash
curl -X POST "https://sds.example.com/api/captures/{capture_uuid}/process_waterfall/" \
  -H "Authorization: Bearer {token}"
```

Response:
```json
{
  "status": "processing",
  "message": "Waterfall processing has been started",
  "task_id": "task-uuid",
  "capture_uuid": "capture-uuid"
}
```

### Check Processing Status

```bash
curl "https://sds.example.com/api/captures/{capture_uuid}/waterfall_status/" \
  -H "Authorization: Bearer {token}"
```

Response:
```json
{
  "status": "completed",
  "capture_uuid": "capture-uuid",
  "waterfall_uuid": "waterfall-uuid",
  "processing_error": null,
  "processed_at": "2024-01-15T10:30:00Z",
  "total_slices": 1000,
  "center_frequency": 1000000000.0,
  "sample_rate": 2000000.0
}
```

### Get Capture with Waterfall Data

```bash
curl "https://sds.example.com/api/captures/{capture_uuid}/" \
  -H "Authorization: Bearer {token}"
```

The response will include waterfall data if available:

```json
{
  "uuid": "capture-uuid",
  "name": "Test Capture",
  "capture_type": "drf",
  "waterfall_data": {
    "uuid": "waterfall-uuid",
    "center_frequency": 1000000000.0,
    "sample_rate": 2000000.0,
    "min_frequency": 999000000.0,
    "max_frequency": 1001000000.0,
    "fft_size": 1024,
    "samples_per_slice": 1024,
    "total_slices": 1000,
    "processing_status": "completed",
    "processed_at": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-15T10:25:00Z"
  }
}
```

## Database Schema

### WaterfallData Model

```python
class WaterfallData(BaseModel):
    capture = models.ForeignKey(Capture, on_delete=models.CASCADE)
    
    # Metadata
    center_frequency = models.FloatField(help_text="Center frequency in Hz")
    sample_rate = models.FloatField(help_text="Sample rate in Hz")
    min_frequency = models.FloatField(help_text="Minimum frequency in Hz")
    max_frequency = models.FloatField(help_text="Maximum frequency in Hz")
    
    # Processing parameters
    fft_size = models.IntegerField(default=1024)
    samples_per_slice = models.IntegerField(default=1024)
    
    # Data storage
    data_file = models.FileField(upload_to="waterfall_data/")
    total_slices = models.IntegerField()
    
    # Processing status
    processing_status = models.CharField(
        choices=[("pending", "Pending"), ("processing", "Processing"), 
                ("completed", "Completed"), ("failed", "Failed")],
        default="pending"
    )
    processing_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
```

## Configuration

### Celery Settings

The system uses existing Celery configuration:

- **Broker**: Redis
- **Result Backend**: Redis
- **Task Time Limit**: 5 minutes
- **Soft Time Limit**: 60 seconds

### Storage

- **Waterfall Data Files**: Stored in MinIO under `waterfall_data/` prefix
- **File Format**: HDF5 with gzip compression
- **Metadata**: Stored in database with file references

## Error Handling

The system includes comprehensive error handling:

1. **Processing Errors**: Captured and stored in the database
2. **File Access Errors**: Handled gracefully with retry logic
3. **Invalid Data**: Validated before processing
4. **Resource Limits**: Respects Celery time limits

## Monitoring

### Logging

All processing steps are logged with appropriate levels:

- **INFO**: Processing start/completion, progress updates
- **WARNING**: Non-critical issues (missing metadata, etc.)
- **ERROR**: Processing failures, file access issues

### Status Tracking

Processing status is tracked in the database:

- `pending`: Task queued but not started
- `processing`: Task currently running
- `completed`: Processing successful
- `failed`: Processing failed with error message

## Testing

Run the test suite:

```bash
cd gateway
python manage.py test sds_gateway.api_methods.tests.test_waterfall_processing
```

Tests cover:
- Model creation and validation
- Processing task success/failure scenarios
- Error handling
- API endpoints
- Unique constraints

## Future Enhancements

1. **Spectrogram Processing**: Extend to support spectrogram generation
2. **Configurable Parameters**: Allow users to specify FFT size and other parameters
3. **Batch Processing**: Process multiple captures simultaneously
4. **Progress Tracking**: Real-time progress updates via WebSockets
5. **Data Compression**: Additional compression options for large datasets

## Integration with SVI

The processed waterfall data can be consumed by the SVI system:

1. **Data Format**: HDF5 files compatible with existing SVI processing
2. **Metadata**: Includes all necessary frequency and timing information
3. **API Access**: SVI can access waterfall data via SDS API endpoints
4. **File Storage**: Leverages existing SDS storage infrastructure

## Performance Considerations

1. **Memory Usage**: Processing large captures may require significant memory
2. **Storage**: Waterfall data files can be large (compressed HDF5)
3. **Processing Time**: Depends on capture size and system resources
4. **Concurrency**: Multiple processing tasks can run simultaneously

## Security

1. **Access Control**: Waterfall data inherits capture permissions
2. **File Security**: Stored in secure MinIO buckets
3. **API Authentication**: All endpoints require authentication
4. **Data Validation**: Input validation prevents malicious data

## Troubleshooting

### Common Issues

1. **Processing Fails**: Check logs for specific error messages
2. **Missing Files**: Verify DigitalRF files exist and are accessible
3. **Memory Errors**: Reduce FFT size or samples per slice
4. **Timeout Errors**: Increase Celery task time limits

### Debug Commands

```bash
# Check Celery worker status
celery -A config.celery_app status

# View task results
celery -A config.celery_app result <task_id>

# Check processing status via API
curl "https://sds.example.com/api/captures/{uuid}/waterfall_status/"
``` 