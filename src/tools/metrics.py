import time
from typing import Dict, Any

from google.cloud import monitoring_v3
from utils.logging import get_logger

logger = get_logger(__name__)

from app.mcp import mcp  # Import the shared FastMCP instance from central app package


@mcp.tool()
def get_metric(
    project_id: str,
    metric_type: str,
    minutes: int = 5,
) -> Dict[str, Any]:
    """
    Retrieve recent metric time series data from Google Cloud Monitoring (Stackdriver).

    This tool allows you to programmatically fetch metrics for a given Google Cloud project,
    such as CPU utilization, memory usage, or custom metrics. It helps you monitor your cloud
    infrastructure or application in real time or near-real time.

    Arguments:
        project_id (str): The Google Cloud project ID to fetch metrics from.
        metric_type (str): The complete metric type, for example
            "compute.googleapis.com/instance/cpu/utilization" or
            "custom.googleapis.com/myapp/performance_score".
        minutes (int, optional): The lookback window for fetching time series, in minutes.
            Defaults to 5. Larger values return more history.

    Returns:
        dict: A dictionary with a "time_series" key, whose value is a list of
            time series records (each with metric labels, resource info, and points).
            If no data is found, the list will be empty.

    Example:
        result = get_metric(
            project_id="my-gcp-project",
            metric_type="compute.googleapis.com/instance/cpu/utilization",
            minutes=10
        )
        # result["time_series"] will contain recent utilization data points

    Notes:
        - Requires proper Google Cloud Monitoring permissions (ADC/service account).
        - Metric type must match one available for the given project.
        - For more metric types, see: https://cloud.google.com/monitoring/api/metrics_gcp

    Raises:
        Exception if the API call fails or authentication is invalid.
    """
    logger.info(
        "Fetching metric '%s' for project '%s' over the last %d minutes.",
        metric_type, project_id, minutes,
    )
    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        now = time.time()
        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": int(now)},
            start_time={"seconds": int(now) - minutes * 60},
        )

        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": f'metric.type="{metric_type}"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )

        time_series = [series.to_dict() for series in results]
        logger.info("Fetched %d time series records.", len(time_series))
        return {"time_series": time_series}
    except Exception as exc:
        logger.exception(
            "Failed to fetch metric '%s' for project '%s'. Exception: %s",
            metric_type, project_id, str(exc)
        )
        raise

# Export mcp to be imported and reused by the project entrypoint
