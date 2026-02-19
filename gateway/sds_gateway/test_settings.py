"""Tests for Django settings configuration."""

from unittest.mock import patch

import pytest
from config.settings.base import (
    _get_brand_image_url,  # pyright: ignore[reportPrivateUsage]
)


class TestGetBrandImageUrl:
    """Test _get_brand_image_url function."""

    def test_empty_path_returns_none(self) -> None:
        with patch("config.settings.base.env.str", return_value=""):
            assert _get_brand_image_url() is None

    def test_whitespace_only_returns_none(self) -> None:
        with patch("config.settings.base.env.str", return_value="   "):
            assert _get_brand_image_url() is None

    def test_http_url_raises_error(self) -> None:
        with (
            patch(
                "config.settings.base.env.str",
                return_value="http://example.com/image.jpg",
            ),
            pytest.raises(ValueError, match="must be a local path"),
        ):
            _get_brand_image_url()

    def test_https_url_raises_error(self) -> None:
        with (
            patch(
                "config.settings.base.env.str",
                return_value="https://example.com/image.jpg",
            ),
            pytest.raises(ValueError, match="must be a local path"),
        ):
            _get_brand_image_url()

    def test_double_slash_url_raises_error(self) -> None:
        with (
            patch(
                "config.settings.base.env.str",
                return_value="//example.com/image.jpg",
            ),
            pytest.raises(ValueError, match="must be a local path"),
        ):
            _get_brand_image_url()

    def test_simple_filename_returns_static_path(self) -> None:
        with patch("config.settings.base.env.str", return_value="logo.png"):
            result = _get_brand_image_url()
            assert result == "/static/logo.png"

    def test_path_with_directory_returns_static_path(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="images/brand/logo.png",
        ):
            result = _get_brand_image_url()
            assert result == "/static/images/brand/logo.png"

    def test_path_with_leading_slash_removes_slash(self) -> None:
        with patch("config.settings.base.env.str", return_value="/images/logo.png"):
            result = _get_brand_image_url()
            assert result == "/static/images/logo.png"

    def test_path_with_leading_static_slash_deduplicates(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="/static/images/logo.png",
        ):
            result = _get_brand_image_url()
            assert result == "/static/images/logo.png"

    def test_path_traversal_parent_raises_error(self, tmp_path) -> None:
        with patch("config.settings.base.APPS_DIR", tmp_path):
            static_dir = tmp_path / "static"
            static_dir.mkdir()

            with (
                patch(
                    "config.settings.base.env.str",
                    return_value="../../../etc/passwd",
                ),
                pytest.raises(ValueError, match="escape static directory"),
            ):
                _get_brand_image_url()

    def test_path_traversal_dot_dot_raises_error(self, tmp_path) -> None:
        with patch("config.settings.base.APPS_DIR", tmp_path):
            static_dir = tmp_path / "static"
            static_dir.mkdir()

            with (
                patch(
                    "config.settings.base.env.str",
                    return_value="images/../../etc/passwd",
                ),
                pytest.raises(ValueError, match="escape static directory"),
            ):
                _get_brand_image_url()

    def test_valid_nested_path_in_static(self, tmp_path) -> None:
        with patch("config.settings.base.APPS_DIR", tmp_path):
            static_dir = tmp_path / "static"
            static_dir.mkdir()

            with patch(
                "config.settings.base.env.str",
                return_value="images/brand/nd-dome.svg",
            ):
                result = _get_brand_image_url()
                assert result == "/static/images/brand/nd-dome.svg"

    def test_deep_nested_path(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="a/b/c/d/e/f/image.png",
        ):
            result = _get_brand_image_url()
            assert result == "/static/a/b/c/d/e/f/image.png"

    def test_path_with_multiple_extensions(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="images/logo.tar.gz",
        ):
            result = _get_brand_image_url()
            assert result == "/static/images/logo.tar.gz"

    def test_svg_file(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="images/brand/logo.svg",
        ):
            result = _get_brand_image_url()
            assert result == "/static/images/brand/logo.svg"

    def test_whitespace_stripped_from_path(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="  images/logo.png  ",
        ):
            result = _get_brand_image_url()
            assert result == "/static/images/logo.png"

    def test_url_with_query_params_raises_error(self) -> None:
        with (
            patch(
                "config.settings.base.env.str",
                return_value="https://example.com/image.png?size=large",
            ),
            pytest.raises(ValueError, match="must be a local path"),
        ):
            _get_brand_image_url()

    def test_data_uri_is_allowed(self) -> None:
        with patch(
            "config.settings.base.env.str",
            return_value="data-uri-image.png",
        ):
            result = _get_brand_image_url()
            assert result == "/static/data-uri-image.png"
