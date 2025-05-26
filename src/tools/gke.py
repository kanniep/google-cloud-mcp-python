import time
from typing import Any

from google.cloud import container_v1
from google.cloud.container_v1.types import Operation, SetNodePoolSizeRequest

from app.mcp import mcp
from src.tools.models.error_response import ErrorResponse
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
    except Exception as exc:
        logger.exception(
            "Failed to fetch GKE from project '%s'.",
            project_id,
        )
        err = ErrorResponse(
            error=str(exc),
            detail=repr(exc),
            context={
                "project_id": project_id,
                "location": location,
            },
        )
        return err.dict()
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


@mcp.tool()
def scale_gke_node_pool(
    project_id: str,
    location: str,  # GKE API uses location (zone or region)
    cluster_name: str,
    node_pool_name: str,
    node_count: int,
) -> dict[str, Any]:
    """Scales a GKE node pool to a specified node count.

    Arguments:
        project_id (str): The Google Cloud project ID.
        location (str): The Google Cloud location (zone or region) of the cluster.
        cluster_name (str): The name of the GKE cluster.
        node_pool_name (str): The name of the node pool to scale.
        node_count (int): The desired number of nodes in the node pool.

    Returns:
        dict: A dictionary containing the API response for the scale operation.
              Note: The response is an Operation object. You might need to
              poll this operation to check for completion status.

    Example:
        result = scale_gke_node_pool(
            project_id="my-gcp-project",
            location="us-central1-a",
            cluster_name="my-cluster",
            node_pool_name="my-node-pool",
            node_count=5
        )
        print(result)

    Notes:
        - Requires proper Google Cloud GKE permissions to modify node pools.

    Raises:
        Exception if the API call fails or authentication is invalid.
    """
    logger.info(
        "Scaling node pool '%s' in cluster '%s' to %d nodes in project '%s', location '%s'.",
        node_pool_name,
        cluster_name,
        node_count,
        project_id,
        location,
    )

    try:
        client = container_v1.ClusterManagerClient()
        # The API expects the node pool resource name in a specific format
        # projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER_NAME/nodePools/NODE_POOL_NAME
        name = f"projects/{project_id}/locations/{location}/clusters/{cluster_name}/nodePools/{node_pool_name}"

        request = SetNodePoolSizeRequest(
            name=name,
            node_count=node_count,
        )

        response = client.set_node_pool_size(request=request)

    except Exception as e:
        logger.exception(
            "Failed to scale node pool '%s' in cluster '%s'. Error: %s",
            node_pool_name,
            cluster_name,
            e,
        )
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "project_id": project_id,
                "location": location,
                "cluster_name": cluster_name,
                "node_pool_name": node_pool_name,
                "node_count": node_count,
            },
        )
        return err.dict()
    else:
        logger.info("Node pool scale operation initiated successfully for '%s'.", name)

        return {
            "operation_id": response.name,
            "project_id": project_id,
            "location": location,
            "cluster_name": cluster_name,
            "node_pool_name": node_pool_name,
            "status": response.status.name,
            "start_time": response.start_time,
            "operation_type": response.operation_type.name,
        }


@mcp.tool()
def wait_gke_operation(
    project_id: str,
    location: str,
    operation_id: str,
    timeout: int = 300,
    poll_interval: int = 5,
) -> dict[str, Any]:
    """
    Waits for a GKE operation to complete.

    Arguments:
        project_id (str): The Google Cloud project ID.
        location (str): The Google Cloud location (zone or region).
        operation_id (str): The ID of the operation to wait for.
        timeout (int): Maximum number of seconds to wait. Default is 300.
        poll_interval (int): Interval (in seconds) between polling. Default is 5.

    Returns:
        dict: Contains status info: 'done' (bool), 'status' (str),
              'error' (str or None), 'timeout' (bool), 'operation_id' (str).
    """
    logger.info(
        "Waiting for GKE operation '%s' in project '%s', location '%s'.",
        operation_id,
        project_id,
        location,
    )

    client = container_v1.ClusterManagerClient()
    parent = f"projects/{project_id}/locations/{location}"
    start_time = time.time()
    try:
        while True:
            op: Operation = client.get_operation(
                name=f"{parent}/operations/{operation_id}",
            )
            logger.debug(
                "Polled operation '%s': status '%s'",
                operation_id,
                op.status.name,
            )
            if op.status == Operation.Status.DONE:
                logger.info("Operation '%s' completed successfully.", operation_id)
                return {
                    "done": True,
                    "operation_id": operation_id,
                    "status": op.status.name,
                    "error": op.error.message
                    if op.error and op.error.message
                    else None,
                    "timeout": False,
                    "project_id": project_id,
                    "location": location,
                }
            if op.status == Operation.Status.ABORTING:
                logger.error(
                    "Operation '%s' finished unsuccessfully: status '%s', error '%s'.",
                    operation_id,
                    op.status.name,
                    op.error.message if op.error else None,
                )
                return {
                    "done": False,
                    "operation_id": operation_id,
                    "status": op.status.name,
                    "error": op.error.message if op.error else "Unknown error",
                    "timeout": False,
                    "project_id": project_id,
                    "location": location,
                }

            if time.time() - start_time > timeout:
                logger.error("Timed out waiting for operation '%s'.", operation_id)
                return {
                    "done": False,
                    "operation_id": operation_id,
                    "status": "TIMEOUT",
                    "error": f"Timeout waiting for operation {operation_id}",
                    "timeout": True,
                    "project_id": project_id,
                    "location": location,
                }

            time.sleep(poll_interval)
    except Exception as exc:
        logger.exception(
            "Error while waiting for GKE operation '%s' in project '%s', location '%s'. Exception: %s",
            operation_id,
            project_id,
            location,
            str(exc),
        )
        return {
            "error": str(exc),
            "context": {
                "project_id": project_id,
                "location": location,
                "operation_id": operation_id,
            },
        }
