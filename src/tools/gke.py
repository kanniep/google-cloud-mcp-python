from typing import Any

from app.mcp import mcp
from google.cloud import container_v1
from utils.logging import get_logger

logger = get_logger(__name__)


@mcp.tool()
def list_gke_clusters(project_id: str, location: str = "-") -> dict[str, Any]:
    """List all GKE clusters accessible with current credentials

    Arguments:
        project_id (str): The Google Cloud project ID to fetch GKE clusters from.
        location (str, optional): The Google Cloud location. Defaults to all locations ("-").

    Returns:
        dict: A dictionary with a "clusters" key, whose value is a list of
            cluster records (each with cluster ID, name, and other details).
            If no clusters are found, the list will be empty.

    Example:
        result = list_gke_clusters(project_id="my-gcp-project")
        print(result)
        # With location
        result = list_gke_clusters(project_id="my-gcp-project", location="us-central1")
        print(result)

    Notes:
        - Requires proper Google Cloud Monitoring permissions (ADC/service account).

    Raises:
        Exception if the API call fails or authentication is invalid.
    """
    logger.info(
        "Fetching GKE clusters from project '%s', location '%s'.",
        project_id,
        location,
    )

    try:
        client = container_v1.ClusterManagerClient()
        parent = f"projects/{project_id}/locations/{location if location else '-'}"
        response = client.list_clusters(parent=parent)
    except Exception:
        logger.exception(
            "Failed to fetch GKE from project '%s'.",
            project_id,
        )
        raise
    else:
        logger.info("Fetched %d GKE cluster records.", len(response.clusters))
        clusters = [
            {
                "id": cluster.id,
                "name": cluster.name,
                "location": cluster.location,
                "tier": cluster.enterprise_config.cluster_tier.name,
                "current_master_version": cluster.current_master_version,
                "current_node_count": cluster.current_node_count,
                "autopilot": {
                    "enabled": cluster.autopilot.enabled,
                },
                "status": cluster.status.name,
                "conditions": list(cluster.conditions),
                "self_link": cluster.self_link,
                "create_time": cluster.create_time,
                "node_pools": [
                    {
                        "name": node_pool.name,
                        "locations": list(node_pool.locations),
                        "version": node_pool.version,
                        "initial_node_count": node_pool.initial_node_count,
                        "self_link": node_pool.self_link,
                        "status": node_pool.status.name,
                        "conditions": list(node_pool.conditions),
                    }
                    for node_pool in cluster.node_pools
                    if not cluster.autopilot.enabled
                ],
            }
            for cluster in response.clusters
        ]

        return {"clusters": clusters}
