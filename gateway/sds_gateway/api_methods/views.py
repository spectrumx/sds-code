from utils.opensearch_client import get_opensearch_client


# Create your views here.
def index_capture_metadata(capture, metadata):
    client = get_opensearch_client()

    # Combine capture fields and additional fields
    document = {
        "channel": capture.channel,
        "capture_type": capture.capture_type,
        **metadata,
    }

    # Index the document in OpenSearch
    client.index(index="capture_metadata", id=capture.uuid, body=document)


# TODO: write an APIView with function to create a Capture obj
# then index the capture metadata in OpenSearch
