"""Test factories for API methods models.

This module provides factory classes for creating test instances of Django models
used in the API methods. It includes factories for Dataset and File models, as well
as utilities for mocking MinIO operations during testing.

The factories use the factory_boy library to generate realistic test data with
faker providers, making tests more robust and realistic.
"""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from django.core.files.base import ContentFile
from factory import Faker
from factory import post_generation
from factory.django import DjangoModelFactory

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.users.tests.factories import UserFactory


class DatasetFactory(DjangoModelFactory):
    """Factory for creating Dataset instances for testing.

    This factory creates realistic Dataset objects with automatically generated
    test data. It uses faker providers to generate random but realistic values
    for fields like names, descriptions, and metadata.

    The factory creates a complete Dataset with all required fields populated,
    including a default owner (User), metadata fields, and proper relationships.

    Attributes:
        uuid: Automatically generated UUID4 identifier
        name: Random sentence with 3 words (e.g., "The quick brown")
        abstract: Random text up to 200 characters
        description: Random text up to 500 characters
        doi: Random UUID4 for DOI identifier
        authors: Fixed list of test authors ["John Doe", "Jane Smith"]
        license: Fixed value "MIT"
        keywords: Fixed list ["RF", "capture", "analysis"]
        institutions: Fixed list ["Example University"]
        release_date: Random datetime
        repository: Random URL
        version: Fixed value "1.0.0"
        website: Random URL
        provenance: Fixed dict {"source": "test"}
        citation: Fixed dict {"title": "Test Dataset"}
        other: Fixed dict {"notes": "Test dataset"}
        owner: Automatically created User instance
        is_deleted: Fixed value False
        is_public: Fixed value False

    Example:
        # Create a basic dataset
        dataset = DatasetFactory()

        # Create a dataset with custom owner
        user = UserFactory()
        dataset = DatasetFactory(owner=user)

        # Create a public dataset
        dataset = DatasetFactory(is_public=True)
    """

    uuid = Faker("uuid4")
    name = Faker("sentence", nb_words=3)
    abstract = Faker("text", max_nb_chars=200)
    description = Faker("text", max_nb_chars=500)
    doi = Faker("uuid4")
    authors = ["John Doe", "Jane Smith"]
    license = "MIT"
    keywords = ["RF", "capture", "analysis"]
    institutions = ["Example University"]
    release_date = Faker("date_time")
    repository = Faker("url")
    version = "1.0.0"
    website = Faker("url")
    provenance = {"source": "test"}
    citation = {"title": "Test Dataset"}
    other = {"notes": "Test dataset"}
    owner = Faker("subfactory", factory=UserFactory)
    is_deleted = False
    is_public = False

    class Meta:
        model = Dataset


class FileFactory(DjangoModelFactory):
    """Factory for creating File instances for testing.

    This factory creates realistic File objects that represent files stored in
    the system. It generates test data for file metadata and creates a Django
    ContentFile for the actual file content.

    The factory creates files with realistic metadata including size, checksums,
    and proper file extensions. It also handles the creation of the Django file
    field with test content.

    Attributes:
        uuid: Automatically generated UUID4 identifier
        directory: Fixed path "/files/test/"
        name: Random filename with .h5 extension (e.g., "data_123.h5")
        media_type: Fixed value "application/x-hdf5"
        permissions: Fixed value "rw-r--r--"
        size: Random integer between 1000 and 1000000 bytes
        sum_blake3: Random SHA256 hash for file checksum
        owner: Automatically created User instance
        is_deleted: Fixed value False
        file: Django ContentFile with test content (created in post_generation)

    Example:
        # Create a basic file
        file = FileFactory()

        # Create a file with custom owner
        user = UserFactory()
        file = FileFactory(owner=user)

        # Create a file with custom name
        file = FileFactory(name="custom_data.h5")

        # Create a file associated with a dataset
        dataset = DatasetFactory()
        file = FileFactory(dataset=dataset)
    """

    uuid = Faker("uuid4")
    directory = "/files/test/"
    name = Faker("file_name", extension="h5")
    media_type = "application/x-hdf5"
    permissions = "rw-r--r--"
    size = Faker("random_int", min=1000, max=1000000)
    sum_blake3 = Faker("sha256")
    owner = Faker("subfactory", factory=UserFactory)
    is_deleted = False

    @post_generation
    def file(self, create, extracted, **kwargs):
        """Generate a Django ContentFile for the file field.

        This post-generation hook creates a Django ContentFile object that
        simulates the actual file content. The ContentFile is created with
        test content and the filename from the factory.

        Args:
            create: Boolean indicating if the object is being created
            extracted: Any extracted value passed to the factory
            **kwargs: Additional keyword arguments

        Note:
            This method is automatically called by factory_boy after the
            File instance is created. It ensures that the file field
            contains a valid Django ContentFile object.
        """
        if not create:
            return

        if extracted:
            self.file = extracted
        else:
            # Create a simple file content
            content = b"test file content"
            self.file = ContentFile(content, name=self.name)

    class Meta:
        model = File


class MockMinIOContext:
    """Context manager for mocking MinIO operations without creating actual objects.

    This context manager provides a clean way to mock MinIO client operations
    during testing. It patches the MinIO client to return dummy data instead
    of performing actual MinIO operations, making tests faster and more reliable.

    The context manager mocks three key MinIO operations:
    - fget_object: Simulates downloading a file from MinIO
    - get_object: Simulates getting an object with streaming capability
    - stat_object: Simulates getting file metadata

    When used as a context manager, it automatically patches the MinIO client
    on entry and restores the original client on exit.

    Attributes:
        file_content: The dummy content to return for MinIO operations
        mock_client: The MagicMock object that replaces the real MinIO client
        mock_patcher: The patch object used to replace get_minio_client

    Example:
        # Basic usage with default content
        with MockMinIOContext():
            file = FileFactory()
            content = download_file(file)  # Returns default dummy content

        # Usage with custom content
        with MockMinIOContext(b"custom file content"):
            file = FileFactory()
            content = download_file(file)  # Returns "custom file content"

        # Usage with multiple files
        with MockMinIOContext(b"file1 content"):
            file1 = FileFactory()
        with MockMinIOContext(b"file2 content"):
            file2 = FileFactory()
    """

    def __init__(self, file_content: bytes | None = None):
        """Initialize the MockMinIOContext.

        Args:
            file_content: Optional custom content for MinIO operations.
                         Defaults to b"dummy minio file content" if not provided.
        """
        self.file_content = file_content or b"dummy minio file content"
        self.mock_client = None
        self.mock_patcher = None

    def __enter__(self):
        """Set up MinIO mocking when entering the context.

        This method:
        1. Creates a MagicMock object to replace the MinIO client
        2. Configures the mock to simulate MinIO operations
        3. Patches the get_minio_client function to return the mock
        4. Returns the mock client for potential further configuration

        Returns:
            MagicMock: The mock MinIO client that replaces the real client
        """
        # Create a mock MinIO client
        self.mock_client = MagicMock()

        # Mock the fget_object method to simulate downloading a file
        def mock_fget_object(bucket_name, object_name, file_path):
            # Write dummy content to the file path
            Path(file_path).write_bytes(self.file_content)

        self.mock_client.fget_object.side_effect = mock_fget_object

        # Mock the get_object method to return a mock response
        mock_response = MagicMock()
        mock_response.stream.return_value = [self.file_content]
        mock_response.close.return_value = None
        mock_response.release_conn.return_value = None
        self.mock_client.get_object.return_value = mock_response

        # Mock the stat_object method to return file metadata
        mock_stat = MagicMock()
        mock_stat.size = 1024  # Default size
        mock_stat.content_type = "application/octet-stream"
        self.mock_client.stat_object.return_value = mock_stat

        # Start patching
        self.mock_patcher = patch(
            "sds_gateway.api_methods.utils.minio_client.get_minio_client"
        )
        mock_get_client = self.mock_patcher.start()
        mock_get_client.return_value = self.mock_client

        return self.mock_client

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up MinIO mocking when exiting the context.

        This method stops the patch that was started in __enter__, restoring
        the original get_minio_client function.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        if self.mock_patcher:
            self.mock_patcher.stop()


def create_file_with_minio_mock(
    file_content: bytes | None = None, **file_kwargs
) -> File:
    """Create a File instance with MinIO mocking enabled.

    This is a convenience function that combines FileFactory creation with
    MinIO mocking. It creates a File instance using FileFactory while ensuring
    that any MinIO operations performed on that file will use mocked data.

    The function wraps FileFactory creation inside a MockMinIOContext, so
    the returned File instance will have its MinIO operations mocked for the
    duration of the context.

    Args:
        file_content: Optional custom content for MinIO operations.
                     If provided, this content will be returned when the file
                     is "downloaded" from MinIO. If None, uses default dummy content.
        **file_kwargs: Additional keyword arguments to pass to FileFactory.
                      These can include any valid FileFactory parameters such as
                      owner, dataset, capture, name, directory, etc.

    Returns:
        File: A File instance created by FileFactory with MinIO mocking enabled.
              The file will have all the standard FileFactory attributes plus
              mocked MinIO operations.

    Example:
        # Create a file with default MinIO content
        file = create_file_with_minio_mock(owner=user)

        # Create a file with custom MinIO content
        file = create_file_with_minio_mock(
            file_content=b"custom content",
            owner=user,
            dataset=dataset,
            name="test.h5"
        )

        # Create a file associated with a capture
        file = create_file_with_minio_mock(
            file_content=b"capture data",
            owner=user,
            capture=capture
        )

    Note:
        This function is equivalent to:
        ```python
        with MockMinIOContext(file_content):
            return FileFactory(**file_kwargs)
        ```
        but provides a more convenient interface for common use cases.
    """
    with MockMinIOContext(file_content):
        return FileFactory(**file_kwargs)
