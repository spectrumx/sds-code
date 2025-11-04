"""Tests for the KeywordsAutocompleteView endpoint."""

import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from rest_framework import status

from sds_gateway.api_methods.models import Dataset
from sds_gateway.users.models import User

# Test constants
HTTP_OK = status.HTTP_200_OK
HTTP_INTERNAL_SERVER_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR
DEFAULT_KEYWORD_LIMIT = 50
TEST_LIMIT = 2


@pytest.mark.django_db
class TestKeywordsAutocompleteView:
    """Tests for the KeywordsAutocompleteView endpoint."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def user1(self) -> User:
        """Create first test user."""
        return User.objects.create_user(
            email="user1@example.com",
            password="testpass123",  # noqa: S106
            name="User 1",
            is_approved=True,
        )

    @pytest.fixture
    def user2(self) -> User:
        """Create second test user."""
        return User.objects.create_user(
            email="user2@example.com",
            password="testpass123",  # noqa: S106
            name="User 2",
            is_approved=True,
        )

    @pytest.fixture
    def user3(self) -> User:
        """Create third test user."""
        return User.objects.create_user(
            email="user3@example.com",
            password="testpass123",  # noqa: S106
            name="User 3",
            is_approved=True,
        )

    @pytest.fixture
    def dataset1(self, user1: User) -> Dataset:
        """Create dataset with keywords for user1."""
        return Dataset.objects.create(
            name="Dataset 1",
            owner=user1,
            description="Test dataset 1",
            keywords=json.dumps(["keyword1", "keyword2", "shared-keyword"]),
            status="draft",
        )

    @pytest.fixture
    def dataset2(self, user2: User) -> Dataset:
        """Create dataset with keywords for user2."""
        return Dataset.objects.create(
            name="Dataset 2",
            owner=user2,
            description="Test dataset 2",
            keywords=json.dumps(["keyword3", "keyword4", "shared-keyword"]),
            status="draft",
        )

    @pytest.fixture
    def dataset3(self, user3: User) -> Dataset:
        """Create dataset with unique keywords for user3."""
        return Dataset.objects.create(
            name="Dataset 3",
            owner=user3,
            description="Test dataset 3",
            keywords=json.dumps(["unique-keyword-user3", "another-unique"]),
            status="draft",
        )

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cache before and after each test."""
        cache.clear()
        yield
        cache.clear()

    def test_retrieves_keywords_from_all_users(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
        dataset3: Dataset,
    ) -> None:
        """Test that keywords from all users are retrieved."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        assert "keywords" in data
        keywords = data["keywords"]

        # Should contain keywords from all users
        assert "keyword1" in keywords  # From user1
        assert "keyword2" in keywords  # From user1
        assert "keyword3" in keywords  # From user2
        assert "keyword4" in keywords  # From user2
        assert "unique-keyword-user3" in keywords  # From user3
        assert "another-unique" in keywords  # From user3
        assert "shared-keyword" in keywords  # From both user1 and user2

    def test_retrieves_keywords_for_different_user(
        self,
        client: Client,
        user2: User,
        dataset1: Dataset,
        dataset2: Dataset,
        dataset3: Dataset,
    ) -> None:
        """Test that user2 can see keywords from user1 and user3."""
        client.force_login(user2)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should contain keywords from all users
        assert "keyword1" in keywords  # From user1
        assert "keyword2" in keywords  # From user1
        assert "keyword3" in keywords  # From user2
        assert "keyword4" in keywords  # From user2
        assert "unique-keyword-user3" in keywords  # From user3
        assert "another-unique" in keywords  # From user3

    def test_keywords_deduplication(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
    ) -> None:
        """Test that duplicate keywords are deduplicated."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # "shared-keyword" appears in both datasets, should only appear once
        assert keywords.count("shared-keyword") == 1
        # All keywords should be unique
        assert len(keywords) == len(set(keywords))

    def test_query_filtering(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
        dataset3: Dataset,
    ) -> None:
        """Test that query parameter filters keywords."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # Filter by "unique"
        response = client.get(url, {"query": "unique"})

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should only contain keywords with "unique" in them
        assert all("unique" in keyword.lower() for keyword in keywords)
        assert "unique-keyword-user3" in keywords
        assert "another-unique" in keywords

        # Should not contain other keywords
        assert "keyword1" not in keywords
        assert "keyword2" not in keywords

    def test_query_filtering_case_insensitive(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
    ) -> None:
        """Test that query filtering is case-insensitive."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # Filter with uppercase
        response = client.get(url, {"query": "KEYWORD"})

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should contain keywords with "keyword" (case-insensitive)
        keyword_matches = [
            "keyword1" in keywords,
            "keyword2" in keywords,
            "keyword3" in keywords,
            "keyword4" in keywords,
        ]
        assert any(keyword_matches)

    def test_limit_parameter(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
        dataset3: Dataset,
    ) -> None:
        """Test that limit parameter limits the number of results."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # Request with limit of 2
        response = client.get(url, {"limit": "2"})

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should have at most TEST_LIMIT keywords
        assert len(keywords) <= TEST_LIMIT

    def test_default_limit(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
        dataset3: Dataset,
    ) -> None:
        """Test that default limit is 50."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should have at most DEFAULT_KEYWORD_LIMIT keywords (default limit)
        assert len(keywords) <= DEFAULT_KEYWORD_LIMIT

    def test_cache_hit(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
    ) -> None:
        """Test that cache is used on subsequent requests."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # First request (cache miss)
        response1 = client.get(url)
        assert response1.status_code == HTTP_OK
        data1 = response1.json()
        keywords1 = set(data1["keywords"])

        # Second request (cache hit)
        response2 = client.get(url)
        assert response2.status_code == HTTP_OK
        data2 = response2.json()
        keywords2 = set(data2["keywords"])

        # Results should be the same
        assert keywords1 == keywords2

    def test_cache_invalidation_on_dataset_create(
        self,
        client: Client,
        user1: User,
        user2: User,
        dataset1: Dataset,
    ) -> None:
        """Test that cache is invalidated when a new dataset is created."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # First request to populate cache
        response1 = client.get(url)
        assert response1.status_code == HTTP_OK

        # Create a new dataset with new keywords
        Dataset.objects.create(
            name="New Dataset",
            owner=user2,
            description="New test dataset",
            keywords=json.dumps(["new-keyword-from-cache-test"]),
            status="draft",
        )

        # Second request should include the new keyword (cache was invalidated)
        response2 = client.get(url)
        assert response2.status_code == HTTP_OK
        data2 = response2.json()
        keywords2 = set(data2["keywords"])

        # Should contain the new keyword
        assert "new-keyword-from-cache-test" in keywords2
        # Should also contain old keywords
        assert "keyword1" in keywords2

    def test_cache_invalidation_on_dataset_update(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
    ) -> None:
        """Test that cache is invalidated when a dataset is updated."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # First request to populate cache
        response1 = client.get(url)
        assert response1.status_code == HTTP_OK

        # Update dataset with new keywords
        dataset1.keywords = json.dumps(["updated-keyword-1", "updated-keyword-2"])
        dataset1.save()

        # Second request should include the updated keywords
        response2 = client.get(url)
        assert response2.status_code == HTTP_OK
        data2 = response2.json()
        keywords2 = set(data2["keywords"])

        # Should contain the updated keywords
        assert "updated-keyword-1" in keywords2
        assert "updated-keyword-2" in keywords2
        # Should not contain old keywords
        assert "keyword1" not in keywords2
        assert "keyword2" not in keywords2

    def test_cache_invalidation_on_dataset_soft_delete(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
    ) -> None:
        """Test that cache is invalidated when a dataset is soft deleted."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # First request to populate cache
        response1 = client.get(url)
        assert response1.status_code == HTTP_OK

        # Soft delete the dataset
        dataset1.is_deleted = True
        dataset1.save()

        # Second request should not include keywords from deleted dataset
        response2 = client.get(url)
        assert response2.status_code == HTTP_OK
        data2 = response2.json()
        keywords2 = set(data2["keywords"])

        # Should not contain keywords from deleted dataset
        assert "keyword1" not in keywords2
        assert "keyword2" not in keywords2

    def test_excludes_deleted_datasets(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
    ) -> None:
        """Test that keywords from deleted datasets are not included."""
        # Soft delete dataset1
        dataset1.is_deleted = True
        dataset1.save()

        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should not contain keywords from deleted dataset
        assert "keyword1" not in keywords
        assert "keyword2" not in keywords

        # Should still contain keywords from non-deleted dataset
        assert "keyword3" in keywords
        assert "keyword4" in keywords

    def test_excludes_empty_keywords(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
    ) -> None:
        """Test that datasets with empty keywords are excluded."""
        # Create dataset with empty keywords (use empty JSON array string)
        Dataset.objects.create(
            name="Empty Keywords Dataset",
            owner=user1,
            keywords=json.dumps([]),  # Empty list, will be stored as "[]"
            status="draft",
        )

        # Create dataset with empty string keywords
        Dataset.objects.create(
            name="Empty String Keywords Dataset",
            owner=user1,
            keywords="",  # Empty string
            status="draft",
        )

        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should only contain keywords from dataset1, not empty/null datasets
        assert "keyword1" in keywords
        assert "keyword2" in keywords

    def test_requires_authentication(
        self,
        client: Client,
        dataset1: Dataset,
    ) -> None:
        """Test that the endpoint requires authentication."""
        url = reverse("users:keywords_autocomplete")

        # Request without authentication
        response = client.get(url)

        # Should redirect to login or return 403/401
        assert response.status_code in [302, 401, 403]

    def test_handles_invalid_limit(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
    ) -> None:
        """Test that invalid limit parameter is handled gracefully."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        # Request with invalid limit (non-numeric)
        response = client.get(url, {"limit": "invalid"})

        # The current implementation uses int() which will raise ValueError
        # which is caught and returns 500
        assert response.status_code == HTTP_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "error" in data

    def test_keywords_sorted(
        self,
        client: Client,
        user1: User,
        dataset1: Dataset,
        dataset2: Dataset,
        dataset3: Dataset,
    ) -> None:
        """Test that keywords are returned in sorted order."""
        client.force_login(user1)
        url = reverse("users:keywords_autocomplete")

        response = client.get(url)

        assert response.status_code == HTTP_OK
        data = response.json()
        keywords = data["keywords"]

        # Should be sorted
        assert keywords == sorted(keywords)
