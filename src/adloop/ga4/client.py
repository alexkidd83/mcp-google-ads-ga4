"""GA4 API client wrapper — thin layer over google-analytics-data and google-analytics-admin."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient as AlphaAdminServiceClient
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    from adloop.config import AdLoopConfig


def get_data_client(config: AdLoopConfig) -> BetaAnalyticsDataClient:
    """Return an authenticated GA4 Data API client."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    from adloop.auth import get_ga4_credentials

    credentials = get_ga4_credentials(config)
    return BetaAnalyticsDataClient(credentials=credentials)


def get_admin_client(config: AdLoopConfig) -> AnalyticsAdminServiceClient:
    """Return an authenticated GA4 Admin API client."""
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient

    from adloop.auth import get_ga4_credentials

    credentials = get_ga4_credentials(config)
    return AnalyticsAdminServiceClient(credentials=credentials)


def get_alpha_admin_client(config: AdLoopConfig) -> AlphaAdminServiceClient:
    """Return an authenticated GA4 Admin API alpha client.

    Required for features only available in the v1alpha API surface,
    such as reporting data annotations.
    """
    from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient

    from adloop.auth import get_ga4_credentials

    credentials = get_ga4_credentials(config)
    return AnalyticsAdminServiceClient(credentials=credentials)
