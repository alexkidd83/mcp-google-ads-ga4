"""GA4 Admin API tools — property details, custom dimensions/metrics, and annotations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adloop.config import AdLoopConfig


def get_property_details(
    config: AdLoopConfig,
    *,
    property_id: str = "",
) -> dict:
    """Return detailed metadata for a GA4 property.

    Includes display name, time zone, currency, industry category,
    service level, create/update timestamps, and parent account.
    """
    from google.analytics.admin_v1beta import GetPropertyRequest

    from adloop.ga4.client import get_admin_client

    client = get_admin_client(config)
    request = GetPropertyRequest(name=property_id)
    prop = client.get_property(request=request)

    return {
        "name": prop.name,
        "display_name": prop.display_name,
        "property_type": prop.property_type.name if prop.property_type else None,
        "time_zone": prop.time_zone,
        "currency_code": prop.currency_code,
        "industry_category": prop.industry_category.name if prop.industry_category else None,
        "service_level": prop.service_level.name if prop.service_level else None,
        "create_time": prop.create_time.isoformat() if prop.create_time else None,
        "update_time": prop.update_time.isoformat() if prop.update_time else None,
        "parent": prop.parent,
        "account": prop.account,
    }


def get_custom_dimensions_and_metrics(
    config: AdLoopConfig,
    *,
    property_id: str = "",
) -> dict:
    """List custom dimensions and custom metrics defined for a GA4 property.

    Uses the Data API metadata endpoint to retrieve all dimensions and metrics,
    then filters to only those with custom_definition=True.
    """
    from adloop.ga4.client import get_data_client

    client = get_data_client(config)
    metadata = client.get_metadata(name=f"{property_id}/metadata")

    custom_dimensions = []
    for dim in metadata.dimensions:
        if dim.custom_definition:
            custom_dimensions.append({
                "api_name": dim.api_name,
                "display_name": dim.ui_name,
                "description": dim.description,
                "category": dim.category,
            })

    custom_metrics = []
    for met in metadata.metrics:
        if met.custom_definition:
            custom_metrics.append({
                "api_name": met.api_name,
                "display_name": met.ui_name,
                "description": met.description,
                "category": met.category,
                "type": met.type_.name if met.type_ else None,
            })

    return {
        "property": property_id,
        "custom_dimensions": custom_dimensions,
        "total_custom_dimensions": len(custom_dimensions),
        "custom_metrics": custom_metrics,
        "total_custom_metrics": len(custom_metrics),
    }


def list_property_annotations(
    config: AdLoopConfig,
    *,
    property_id: str = "",
) -> dict:
    """List reporting data annotations for a GA4 property.

    Annotations are notes attached to specific dates or date ranges in GA4,
    typically used to record events such as service releases, marketing campaign
    launches or changes, and traffic spikes or drops due to external factors.

    Returns a list of annotations with name, title, description, color,
    date or date range, and whether the annotation was system-generated.
    """
    from google.analytics.admin_v1alpha import ListReportingDataAnnotationsRequest

    from adloop.ga4.client import get_alpha_admin_client

    client = get_alpha_admin_client(config)
    request = ListReportingDataAnnotationsRequest(parent=property_id)
    pager = client.list_reporting_data_annotations(request=request)

    annotations = []
    for annotation in pager:
        # Each annotation has either annotation_date (single day) or
        # annotation_date_range (start + end date) — only one is set.
        # google.type.Date fields expose .year/.month/.day integers and must
        # be serialised explicitly; they are not datetime objects.
        if annotation.annotation_date:
            d = annotation.annotation_date
            date_info = {"date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}"}
        elif annotation.annotation_date_range:
            s = annotation.annotation_date_range.start_date
            e = annotation.annotation_date_range.end_date
            date_info = {
                "start_date": f"{s.year:04d}-{s.month:02d}-{s.day:02d}",
                "end_date": f"{e.year:04d}-{e.month:02d}-{e.day:02d}",
            }
        else:
            date_info = {}

        annotations.append({
            "name": annotation.name,
            "title": annotation.title,
            "description": annotation.description,
            "color": annotation.color.name if annotation.color else None,
            "system_generated": annotation.system_generated,
            **date_info,
        })

    return {
        "property": property_id,
        "annotations": annotations,
        "total_annotations": len(annotations),
    }
