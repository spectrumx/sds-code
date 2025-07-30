"""Integration tests for dataset functionality."""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests
from spectrumx import Client
from spectrumx.api.datasets import DatasetAPI
from spectrumx.errors import DatasetError
from spectrumx.models.datasets import Dataset


class TestDatasetAPI:
    """Test cases for DatasetAPI."""

    def setup_method(self):
        """Set up test fixtures."""
        self.gateway = Mock()
        self.dataset_api = DatasetAPI(gateway=self.gateway, dry_run=False, verbose=True)

    def test_download_dataset_success(self):
        """Test successful dataset download."""
        dataset_uuid = uuid.uuid4()

        # Mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"zip content"]

        self.gateway.download_dataset.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_dataset.zip"

            result = self.dataset_api.download(dataset_uuid, output_path)

            assert result == output_path
            assert output_path.exists()
            assert output_path.read_bytes() == b"zip content"

            self.gateway.download_dataset.assert_called_once_with(
                dataset_uuid=dataset_uuid
            )

    def test_download_dataset_file_system_error(self):
        """Test dataset download with file system error."""
        dataset_uuid = uuid.uuid4()

        # Mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"zip content"]

        self.gateway.download_dataset.return_value = mock_response

        # Try to write to a non-existent directory
        output_path = Path("/non/existent/path/dataset.zip")

        with pytest.raises(DatasetError, match="File system error downloading dataset"):
            self.dataset_api.download(dataset_uuid, output_path)

    def test_download_dataset_network_error(self):
        """Test dataset download with network error."""
        dataset_uuid = uuid.uuid4()
        self.gateway.download_dataset.side_effect = requests.RequestException(
            "Network error"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_dataset.zip"

            with pytest.raises(DatasetError, match="Network error downloading dataset"):
                self.dataset_api.download(dataset_uuid, output_path)

    def test_download_dataset_dry_run(self):
        """Test dataset download in dry run mode."""
        self.dataset_api.dry_run = True
        dataset_uuid = uuid.uuid4()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_dataset.zip"

            result = self.dataset_api.download(dataset_uuid, output_path)

            assert result == output_path
            assert output_path.exists()
            assert output_path.read_bytes() == b"# Dry run: dummy dataset ZIP content"

            # Should not call gateway in dry run mode
            self.gateway.download_dataset.assert_not_called()


class TestClientDatasetIntegration:
    """Integration tests for Client dataset functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = Client(host="localhost", verbose=True)

    def test_download_dataset_success(self):
        """Test successful dataset download through client."""
        dataset_uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

        with patch.object(self.client.datasets, "download") as mock_download:
            mock_download.return_value = Path("/tmp/test.zip")

            result = self.client.download_dataset(
                dataset_uuid=dataset_uuid, to_local_path="/tmp/test.zip"
            )

            assert result == Path("/tmp/test.zip")
            mock_download.assert_called_once_with(
                dataset_uuid=uuid.UUID(dataset_uuid),
                to_local_path=Path("/tmp/test.zip"),
            )

    def test_download_dataset_with_string_uuid(self):
        """Test dataset download with string UUID."""
        dataset_uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

        with patch.object(self.client.datasets, "download") as mock_download:
            mock_download.return_value = Path("/tmp/test.zip")

            result = self.client.download_dataset(
                dataset_uuid=dataset_uuid, to_local_path="/tmp/test.zip"
            )

            # Should convert string UUID to UUID object
            call_args = mock_download.call_args
            assert call_args[1]["dataset_uuid"] == uuid.UUID(dataset_uuid)

    def test_download_dataset_error_propagation(self):
        """Test that dataset errors are properly propagated."""
        dataset_uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

        with patch.object(self.client.datasets, "download") as mock_download:
            mock_download.side_effect = DatasetError("Test error")

            with pytest.raises(DatasetError, match="Test error"):
                self.client.download_dataset(
                    dataset_uuid=dataset_uuid, to_local_path="/tmp/test.zip"
                )

    def test_client_verbose_setter_affects_datasets(self):
        """Test that client verbose setter affects dataset API."""
        self.client.verbose = True
        assert self.client.datasets.verbose is True

        self.client.verbose = False
        assert self.client.datasets.verbose is False

    def test_client_dry_run_setter_affects_datasets(self):
        """Test that client dry_run setter affects dataset API."""
        self.client.dry_run = True
        assert self.client.datasets.dry_run is True

        self.client.dry_run = False
        assert self.client.datasets.dry_run is False


class TestDatasetModel:
    """Test cases for Dataset model."""

    def test_dataset_creation(self):
        """Test Dataset model creation."""
        dataset = Dataset(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            abstract="Test abstract",
            authors=["John Doe"],
            keywords=["test", "data"],
            institutions=["Test University"],
        )

        assert dataset.name == "Test Dataset"
        assert dataset.authors == ["John Doe"]
        assert dataset.keywords == ["test", "data"]
        assert dataset.institutions == ["Test University"]

    def test_dataset_default_values(self):
        """Test Dataset model default values."""
        dataset = Dataset()

        assert dataset.uuid is None
        assert dataset.name is None
        assert dataset.is_deleted is False
        assert dataset.is_public is False
