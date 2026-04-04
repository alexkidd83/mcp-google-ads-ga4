"""Tests for GA4 Admin API tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adloop.config import AdLoopConfig, GA4Config
from adloop.ga4.admin import (
    get_custom_dimensions_and_metrics,
    get_property_details,
    list_property_annotations,
)


@pytest.fixture
def config():
    return AdLoopConfig(ga4=GA4Config(property_id="properties/123456"))


class TestGetPropertyDetails:
    @patch("adloop.ga4.client.get_admin_client")
    def test_calls_get_property_with_correct_request(self, mock_get_client, config):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_property.return_value = SimpleNamespace(
            name="properties/123456",
            display_name="My Property",
            property_type=SimpleNamespace(name="PROPERTY_TYPE_ORDINARY"),
            time_zone="America/New_York",
            currency_code="USD",
            industry_category=SimpleNamespace(name="TECHNOLOGY"),
            service_level=SimpleNamespace(name="GOOGLE_ANALYTICS_STANDARD"),
            create_time=None,
            update_time=None,
            parent="accounts/999",
            account="accounts/999",
        )

        result = get_property_details(config, property_id="properties/123456")

        # Verify the client was called with the right property name
        call_kwargs = mock_client.get_property.call_args
        request = call_kwargs.kwargs.get("request") or call_kwargs.args[0]
        assert request.name == "properties/123456"

        # Verify return dict shape
        assert result["name"] == "properties/123456"
        assert result["display_name"] == "My Property"
        assert result["time_zone"] == "America/New_York"
        assert result["currency_code"] == "USD"
        assert result["parent"] == "accounts/999"
        assert result["account"] == "accounts/999"

    @patch("adloop.ga4.client.get_admin_client")
    def test_handles_none_optional_fields(self, mock_get_client, config):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_property.return_value = SimpleNamespace(
            name="properties/123456",
            display_name="Minimal",
            property_type=None,
            time_zone="UTC",
            currency_code="EUR",
            industry_category=None,
            service_level=None,
            create_time=None,
            update_time=None,
            parent=None,
            account=None,
        )

        result = get_property_details(config, property_id="properties/123456")

        assert result["property_type"] is None
        assert result["industry_category"] is None
        assert result["service_level"] is None
        assert result["create_time"] is None


class TestGetCustomDimensionsAndMetrics:
    @patch("adloop.ga4.client.get_data_client")
    def test_filters_by_custom_definition(self, mock_get_client, config):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.get_metadata.return_value = SimpleNamespace(
            dimensions=[
                SimpleNamespace(
                    custom_definition=True,
                    api_name="customEvent:my_dim",
                    ui_name="My Dimension",
                    description="A custom dimension",
                    category="Custom",
                ),
                SimpleNamespace(
                    custom_definition=False,
                    api_name="date",
                    ui_name="Date",
                    description="The date",
                    category="Time",
                ),
            ],
            metrics=[
                SimpleNamespace(
                    custom_definition=True,
                    api_name="customEvent:my_metric",
                    ui_name="My Metric",
                    description="A custom metric",
                    category="Custom",
                    type_=SimpleNamespace(name="TYPE_INTEGER"),
                ),
                SimpleNamespace(
                    custom_definition=False,
                    api_name="sessions",
                    ui_name="Sessions",
                    description="Session count",
                    category="Session",
                    type_=SimpleNamespace(name="TYPE_INTEGER"),
                ),
            ],
        )

        result = get_custom_dimensions_and_metrics(
            config, property_id="properties/123456"
        )

        # Verify it called get_metadata with the right name
        mock_client.get_metadata.assert_called_once_with(
            name="properties/123456/metadata"
        )

        # Only custom_definition=True items should be included
        assert result["total_custom_dimensions"] == 1
        assert result["custom_dimensions"][0]["api_name"] == "customEvent:my_dim"

        assert result["total_custom_metrics"] == 1
        assert result["custom_metrics"][0]["api_name"] == "customEvent:my_metric"
        assert result["custom_metrics"][0]["type"] == "TYPE_INTEGER"

        assert result["property"] == "properties/123456"

    @patch("adloop.ga4.client.get_data_client")
    def test_empty_metadata_returns_zero_counts(self, mock_get_client, config):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_metadata.return_value = SimpleNamespace(
            dimensions=[], metrics=[]
        )

        result = get_custom_dimensions_and_metrics(
            config, property_id="properties/123456"
        )

        assert result["total_custom_dimensions"] == 0
        assert result["total_custom_metrics"] == 0
        assert result["custom_dimensions"] == []
        assert result["custom_metrics"] == []

    @patch("adloop.ga4.client.get_data_client")
    def test_no_custom_definitions_returns_zero(self, mock_get_client, config):
        """All dimensions/metrics have custom_definition=False."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_metadata.return_value = SimpleNamespace(
            dimensions=[
                SimpleNamespace(
                    custom_definition=False,
                    api_name="date",
                    ui_name="Date",
                    description="The date",
                    category="Time",
                ),
            ],
            metrics=[
                SimpleNamespace(
                    custom_definition=False,
                    api_name="sessions",
                    ui_name="Sessions",
                    description="Session count",
                    category="Session",
                    type_=SimpleNamespace(name="TYPE_INTEGER"),
                ),
            ],
        )

        result = get_custom_dimensions_and_metrics(
            config, property_id="properties/123456"
        )

        assert result["total_custom_dimensions"] == 0
        assert result["total_custom_metrics"] == 0


# ---------------------------------------------------------------------------
# Test plan for list_property_annotations
# ---------------------------------------------------------------------------
# 1. Happy path — annotation with a single date (annotation_date oneof)
# 2. Happy path — annotation with a date range (annotation_date_range oneof)
# 3. Annotation with neither date field set (edge case — empty date_info)
# 4. Empty pager — no annotations at all
# 5. Annotation with no color (color is None/unset)
# 6. system_generated flag is preserved correctly
# Remaining gaps: integration against live API; pagination beyond single page.
# ---------------------------------------------------------------------------


class TestListPropertyAnnotations:
    @patch("adloop.ga4.client.get_alpha_admin_client")
    def test_annotation_with_single_date(self, mock_get_client, config):
        """Annotation carrying annotation_date is serialised to ISO format."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        date_obj = SimpleNamespace(year=2025, month=6, day=15)
        mock_annotation = SimpleNamespace(
            name="properties/123456/reportingDataAnnotations/1",
            title="GA4 launch",
            description="Launched new GA4 property",
            color=SimpleNamespace(name="BLUE"),
            system_generated=False,
            annotation_date=date_obj,
            annotation_date_range=None,
        )
        mock_client.list_reporting_data_annotations.return_value = [mock_annotation]

        result = list_property_annotations(config, property_id="properties/123456")

        assert result["property"] == "properties/123456"
        assert result["total_annotations"] == 1
        ann = result["annotations"][0]
        assert ann["name"] == "properties/123456/reportingDataAnnotations/1"
        assert ann["title"] == "GA4 launch"
        assert ann["date"] == "2025-06-15"
        assert "start_date" not in ann
        assert ann["color"] == "BLUE"
        assert ann["system_generated"] is False

    @patch("adloop.ga4.client.get_alpha_admin_client")
    def test_annotation_with_date_range(self, mock_get_client, config):
        """Annotation carrying annotation_date_range is serialised to ISO start/end."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        start = SimpleNamespace(year=2025, month=1, day=1)
        end = SimpleNamespace(year=2025, month=1, day=7)
        mock_annotation = SimpleNamespace(
            name="properties/123456/reportingDataAnnotations/2",
            title="Holiday campaign",
            description="Week-long holiday promo",
            color=SimpleNamespace(name="GREEN"),
            system_generated=False,
            annotation_date=None,
            annotation_date_range=SimpleNamespace(start_date=start, end_date=end),
        )
        mock_client.list_reporting_data_annotations.return_value = [mock_annotation]

        result = list_property_annotations(config, property_id="properties/123456")

        ann = result["annotations"][0]
        assert ann["start_date"] == "2025-01-01"
        assert ann["end_date"] == "2025-01-07"
        assert "date" not in ann

    @patch("adloop.ga4.client.get_alpha_admin_client")
    def test_annotation_with_no_date_field(self, mock_get_client, config):
        """Annotation with neither date field produces no date keys."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_annotation = SimpleNamespace(
            name="properties/123456/reportingDataAnnotations/3",
            title="Undated note",
            description="",
            color=None,
            system_generated=False,
            annotation_date=None,
            annotation_date_range=None,
        )
        mock_client.list_reporting_data_annotations.return_value = [mock_annotation]

        result = list_property_annotations(config, property_id="properties/123456")

        ann = result["annotations"][0]
        assert "date" not in ann
        assert "start_date" not in ann
        assert "end_date" not in ann
        assert ann["color"] is None

    @patch("adloop.ga4.client.get_alpha_admin_client")
    def test_empty_annotations_returns_zero_total(self, mock_get_client, config):
        """Empty pager returns empty list and zero count."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list_reporting_data_annotations.return_value = []

        result = list_property_annotations(config, property_id="properties/123456")

        assert result["total_annotations"] == 0
        assert result["annotations"] == []
        assert result["property"] == "properties/123456"

    @patch("adloop.ga4.client.get_alpha_admin_client")
    def test_system_generated_flag_preserved(self, mock_get_client, config):
        """system_generated=True is faithfully included in output."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        date_obj = SimpleNamespace(year=2024, month=12, day=1)
        mock_annotation = SimpleNamespace(
            name="properties/123456/reportingDataAnnotations/99",
            title="Auto-generated",
            description="System event",
            color=SimpleNamespace(name="ORANGE"),
            system_generated=True,
            annotation_date=date_obj,
            annotation_date_range=None,
        )
        mock_client.list_reporting_data_annotations.return_value = [mock_annotation]

        result = list_property_annotations(config, property_id="properties/123456")

        assert result["annotations"][0]["system_generated"] is True
        assert result["annotations"][0]["color"] == "ORANGE"

    @patch("adloop.ga4.client.get_alpha_admin_client")
    def test_request_uses_property_as_parent(self, mock_get_client, config):
        """list_reporting_data_annotations is called with parent=property_id."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list_reporting_data_annotations.return_value = []

        list_property_annotations(config, property_id="properties/999")

        call_kwargs = mock_client.list_reporting_data_annotations.call_args
        request = call_kwargs.kwargs.get("request") or call_kwargs.args[0]
        assert request.parent == "properties/999"
