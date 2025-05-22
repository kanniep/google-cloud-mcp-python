import time
from typing import Dict, Any

from google.cloud import monitoring_v3
from utils.logging import get_logger
from google.protobuf.json_format import MessageToDict

logger = get_logger(__name__)

from app.mcp import mcp  # Import the shared FastMCP instance from central app package


@mcp.tool()
def get_metric(
    project_id: str,
    metric_type: str,
    minutes: int = 5,
    resource_label: str | None = None,
    resource_label_value: str | None = None,
) -> Dict[str, Any]:
    """
    Retrieve recent metric time series data from Google Cloud Monitoring (Stackdriver).

    This AI-friendly tool fetches metrics from a specified Google Cloud project (like CPU/memory utilization, custom metrics)
    for a recent time window, with fine-grained optional filtering by resource labels (e.g., specific Cloud Run service).

    Args:
        project_id (str): Google Cloud project ID containing the monitored resources.
        metric_type (str): Full metric type string, e.g., "compute.googleapis.com/instance/cpu/utilization",
            "run.googleapis.com/container/cpu/utilizations", or "custom.googleapis.com/myapp/performance_score".
        minutes (int, optional): Minutes of history to fetch, counting backwards from now (default: 5).
            Increasing returns more/folder data points.
        resource_label (str, optional): Resource label key to filter on.
            Examples: "instance_id" for GCE VM, "service_name" for Cloud Run services, "cluster_name" for GKE, etc.
            (Default: None — do not filter by any resource label.)
        resource_label_value (str, optional): Value for the provided resource_label.
            If set, only metric data matching both label and value are included.

    Returns:
        dict: {"time_series": [...]} where the value is a list of time series records as dictionaries.
            Each record contains full metric labels, resource info, points, etc.
            If no matching data is found, the list will be empty.

    Example Usage:
        # 1. Get recent average CPU utilization across all VM instances:
        get_metric(
            project_id="my-gcp-project",
            metric_type="compute.googleapis.com/instance/cpu/utilization"
        )
        # 2. Get CPU utilization for a specific Cloud Run service named 'platform-portal':
        get_metric(
            project_id="my-gcp-project",
            metric_type="run.googleapis.com/container/cpu/utilizations",
            resource_label="service_name",
            resource_label_value="platform-portal"
        )
        # 3. Fetch a custom metric for a GKE cluster:
        get_metric(
            project_id="my-gcp-project",
            metric_type="custom.googleapis.com/myapp/performance_score",
            resource_label="cluster_name",
            resource_label_value="my-cluster"
        )

    Guidance for AI usage:
        - Always specify the metric_type explicitly and correctly according to the resource (see GCP Monitoring docs).
        - If filtering for a specific resource (service, instance, cluster, etc.), use resource_label & resource_label_value.
        - Example resource labels by metric type:
            Cloud Run:         service_name, location
            GKE Cluster:       cluster_name, location, namespace_name
            Compute Engine VM: instance_id, zone
        - If unsure about available labels for a metric, refer to its schema at
          https://cloud.google.com/monitoring/api/metrics_gcp
        - You DO NOT need to specify resource_label/value unless focused on one resource (most "per-service" or "per-pod" queries do require it).

    Notes:
        - Requires Google Cloud Monitoring permissions (ADC or service account).
        - The metric_type and label combination must match at least one resource instance.
        - See all built-in metrics: https://cloud.google.com/monitoring/api/metrics_gcp

    Raises:
        Exception if the API call fails, or if authentication or query is invalid.
    """
    logger.info(
        "Fetching metric '%s' for project '%s' over the last %d minutes.",
        metric_type,
        project_id,
        minutes,
    )
    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        now = time.time()
        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": int(now)},
            start_time={"seconds": int(now) - minutes * 60},
        )

        metric_filter = f'metric.type="{metric_type}"'
        if resource_label and resource_label_value:
            metric_filter += (
                f' AND resource.label.{resource_label}="{resource_label_value}"'
            )

        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": metric_filter,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )

        time_series = [MessageToDict(series._pb) for series in results]
        logger.info("Fetched %d time series records.", len(time_series))
        return {"time_series": time_series}
    except Exception as exc:
        logger.exception(
            "Failed to fetch metric '%s' for project '%s'. Exception: %s",
            metric_type,
            project_id,
            str(exc),
        )
        raise


# Export mcp to be imported and reused by the project entrypoint
