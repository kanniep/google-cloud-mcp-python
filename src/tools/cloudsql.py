from typing import Any
import time

from app.mcp import mcp
from utils.logging import get_logger
from dataclasses import dataclass, field
from datetime import datetime

logger = get_logger(__name__)

@dataclass
class GcpCloudSQLItem:
    name: str
    database_type: str
    database_version: str
    status: str
    zone: str
    is_replica: bool
    is_ha_enabled: bool
    is_ssl_enabled: bool
    disk_size: int
    disk_type: str
    machine_type: str
    create_time: datetime | None
    internal_ip_address: str | None = None
    public_ip_address: str | None = None
    ma_reschedulable: bool | None = None
    ma_start_time: datetime | None = None
    ma_deadline_time: datetime | None = None
    ma_version: str | None = None
    ma_available_version: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, app_name: str, project_id: str, instance: dict) -> "GcpCloudSQLItem":
        def __get_status(instance: dict) -> str:
            return (
                "RUNNING"
                if instance.get("settings", {}).get("activationPolicy") == "ALWAYS"
                else "STOPPED"
            )

        def __get_db_type(db_type: str) -> str:
            if db_type.upper() == "MYSQL":
                return "MySQL"
            if db_type.upper() == "POSTGRES":
                return "Postgres"
            return db_type.capitalize()

        settings = instance.get("settings", {})
        version_splited = instance.get("databaseVersion", "").split("_")

        # RFC3339/ISO parser, safe fallback
        def _get_dt(dt_str):
            if not dt_str:
                return None
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1]
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(dt_str)
            except Exception:
                return None

        item = GcpCloudSQLItem(
            name=instance.get("name", ""),
            database_type=__get_db_type(version_splited[0]) if version_splited and version_splited[0] else "",
            database_version=".".join(version_splited[1:]) if len(version_splited) > 1 else "",
            status=__get_status(instance),
            zone=instance.get("gceZone", ""),
            is_replica=instance.get("instanceType") == "READ_REPLICA_INSTANCE",
            is_ha_enabled=settings.get("availabilityType") == "REGIONAL",
            is_ssl_enabled=settings.get("ipConfiguration", {}).get(
                "sslMode",
                "ALLOW_UNENCRYPTED_AND_ENCRYPTED",
            ) == "TRUSTED_CLIENT_CERTIFICATE_REQUIRED",
            disk_size=int(settings.get("dataDiskSizeGb", 0)),
            disk_type=settings.get("dataDiskType", ""),
            machine_type=settings.get("tier", ""),
            create_time=_get_dt(instance.get("createTime", "")),
        )
        for ip_addr in instance.get("ipAddresses", []):
            if ip_addr.get("type") == "PRIVATE":
                item.internal_ip_address = ip_addr.get("ipAddress")
            elif ip_addr.get("type") == "PRIMARY":
                item.public_ip_address = ip_addr.get("ipAddress")
        if "scheduledMaintenance" in instance:
            sm = instance["scheduledMaintenance"]
            item.ma_reschedulable = sm.get("canReschedule") is True
            start_time = sm.get("startTime")
            deadline_time = sm.get("scheduleDeadlineTime")
            item.ma_start_time = _get_dt(start_time) if start_time else None
            item.ma_deadline_time = _get_dt(deadline_time) if deadline_time else None
            item.ma_version = instance.get("maintenanceVersion")
            item.ma_available_version = instance.get("availableMaintenanceVersions", [])
        return item

    def asdict(self) -> dict:
        # Turn dataclass into dict with proper time serialization
        d = self.__dict__.copy()
        for k in ("create_time", "ma_start_time", "ma_deadline_time"):
            v = d.get(k)
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

@mcp.tool()
def start_cloudsql_instance(project_id: str, instance_name: str) -> dict[str, Any]:
    """
    Start a stopped CloudSQL instance in the given GCP project.

    Changes the instance's activation policy to 'ALWAYS' to start the instance, using Cloud SQL Admin API's patch method.
    This is the officially supported and robust approach to starting a CloudSQL instance.

    Arguments:
        project_id (str): Google Cloud project ID.
        instance_name (str): Name of the CloudSQL instance to start.

    Returns:
        dict: {"status": "STARTING", "instance": instance_name, "operation": operation_id}
            - "status": Status string — "STARTING" if the request was sent.
            - "instance": Name of the instance being started.
            - "operation": GCP operation ID (track this for completion/status).

    Example:
        result = start_cloudsql_instance("ccoe-lab", "testdb1")
        # result['operation'] is the ID you can poll with the GCP API for job completion.

    Notes:
        - Requires CloudSQL Admin permissions and valid ADC.
        - Uses `settings.activationPolicy = "ALWAYS"` to start.
        - https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/instances/patch

    Raises:
        Exception if the API call fails, authentication error, or instance does not exist.
    """
    logger.info("Requesting start for CloudSQL instance '%s' in project '%s'.", instance_name, project_id)
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")
    try:
        service = build("sqladmin", "v1beta4", cache_discovery=False)
        # Fetch the current instance config
        instance = service.instances().get(project=project_id, instance=instance_name).execute()
        # Set activationPolicy to ALWAYS to start
        instance['settings']['activationPolicy'] = 'ALWAYS'
        # Use patch to update only the activationPolicy setting
        patch_body = {
            "settings": {"activationPolicy": "ALWAYS"}
        }
        response = service.instances().patch(project=project_id, instance=instance_name, body=patch_body).execute()
        operation_id = response.get("name", "")
        logger.info("Start (patch) requested for instance '%s'. Operation ID: %s", instance_name, operation_id)
        return {"status": "STARTING", "instance": instance_name, "operation": operation_id}
    except Exception as exc:
        logger.exception("Failed to start CloudSQL instance '%s' for project '%s' via patch: %s", instance_name, project_id, str(exc))
        raise

@mcp.tool()
def stop_cloudsql_instance(project_id: str, instance_name: str) -> dict[str, Any]:
    """
    Stop a running CloudSQL instance in the given GCP project.

    Changes the instance's activation policy to 'NEVER' to stop the instance, using Cloud SQL Admin API's patch method.
    This is the officially supported and robust approach to stopping a CloudSQL instance.

    Arguments:
        project_id (str): Google Cloud project ID.
        instance_name (str): Name of the CloudSQL instance to stop.

    Returns:
        dict: {"status": "STOPPING", "instance": instance_name, "operation": operation_id}
            - "status": Status string — "STOPPING" if the request was sent.
            - "instance": Name of the instance being stopped.
            - "operation": GCP operation ID (track this for completion/status).

    Example:
        result = stop_cloudsql_instance("ccoe-lab", "testdb1")
        # result['operation'] is the ID you can poll with the GCP API for job completion.

    Notes:
        - Requires CloudSQL Admin permissions and valid ADC.
        - Uses `settings.activationPolicy = "NEVER"` to stop.
        - https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/instances/patch
        - Not all instance types can be stopped (manual/2nd gen, not replicas).

    Raises:
        Exception if the API call fails, authentication error, or instance does not exist.
    """
    logger.info("Requesting stop for CloudSQL instance '%s' in project '%s'.", instance_name, project_id)
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")
    try:
        service = build("sqladmin", "v1beta4", cache_discovery=False)
        # Fetch the current instance config
        instance = service.instances().get(project=project_id, instance=instance_name).execute()
        # Set activationPolicy to NEVER to stop
        instance['settings']['activationPolicy'] = 'NEVER'
        # Use patch to update only the activationPolicy setting
        patch_body = {
            "settings": {"activationPolicy": "NEVER"}
        }
        response = service.instances().patch(project=project_id, instance=instance_name, body=patch_body).execute()
        operation_id = response.get("name", "")
        logger.info("Stop (patch) requested for instance '%s'. Operation ID: %s", instance_name, operation_id)
        return {"status": "STOPPING", "instance": instance_name, "operation": operation_id}
    except Exception as exc:
        logger.exception("Failed to stop CloudSQL instance '%s' for project '%s' via patch: %s", instance_name, project_id, str(exc))
        raise

@mcp.tool()
def get_cloudsql_instance(project_id: str, instance_name: str) -> dict[str, Any]:
    """
    Get details of a specific CloudSQL instance in a given GCP project.

    Fetches full metadata for an instance (configuration, status, endpoints, maintenance, etc.).
    Useful for automation, dashboards, troubleshooting, or compliance audits.

    Arguments:
        project_id (str): Google Cloud project ID.
        instance_name (str): Name of the CloudSQL instance to get details for.

    Returns:
        dict: All details as keys (see example), or error explanation.
            - Structure: matches asdict() of GcpCloudSQLItem (name, type, version, status, ips, zone, etc.)

    Example:
        result = get_cloudsql_instance("ccoe-lab", "testdb1")
        # result['name'], result['status'], result['database_type'], etc.

    Notes:
        - Requires CloudSQL Viewer/Admin permissions and valid ADC.
        - See API: https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/instances/get

    Raises:
        Exception if the API call fails, authentication error, or instance does not exist.
    """
    logger.info(
        "Getting CloudSQL instance '%s' in project '%s'.", instance_name, project_id
    )
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")

    try:
        service = build("sqladmin", "v1beta4", cache_discovery=False)
        request = service.instances().get(project=project_id, instance=instance_name)
        response = request.execute()
        item = GcpCloudSQLItem.build(app_name=project_id, project_id=project_id, instance=response)
        logger.info("Fetched CloudSQL instance: '%s'.", instance_name)
        return item.asdict()
    except Exception as exc:
        logger.exception(
            "Failed to get CloudSQL instance '%s' for project '%s': %s",
            instance_name,
            project_id,
            str(exc),
        )
        raise

@mcp.tool()
def wait_cloudsql_operation(
    project_id: str,
    operation_id: str,
    poll_interval: int = 2,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Polls a Cloud SQL Admin API operation until it is DONE or times out.

    Use this tool to wait for completion of asynchronous Cloud SQL operations
    (e.g., start/stop/patch/create/delete) by operation ID. Returns the final
    operation resource state, including errors if any.

    Arguments:
        project_id (str): Google Cloud project ID where the operation resides.
        operation_id (str): The GCP operation ID returned by an async request.
        poll_interval (int, optional): Seconds between polls (default: 2, min: 1, max: reasonable).
            - Make this larger for slow ops (reduce API calls); smaller for responsiveness.
        timeout (int, optional): Maximum seconds to wait before giving up (default: 300).
            - Adjust for fast/slow environments (quick tests: reduce; production: raise for safety).

    Returns:
        dict: The final state of the operation resource as returned by the API.
            - If successful, {"status": "DONE", ...}.
            - If timeout/error, includes error details.

    Quick Reference:
        # Wait up to default 5 minutes, 2s intervals (recommended default)
        result = wait_cloudsql_operation("ccoe-lab", "opid1234")

        # Wait up to 10 minutes, 5s intervals (heavy/slow ops)
        result = wait_cloudsql_operation("ccoe-lab", "opid1234", poll_interval=5, timeout=600)

        # For fast test/dev fail-fast: 60s total, 1s interval
        result = wait_cloudsql_operation("ccoe-lab", "opid1234", poll_interval=1, timeout=60)
        # Inspect result['status'] (should be "DONE" for successful completion)

    Notes:
        - poll_interval and timeout are fully configurable for any automation needs.
        - See API: https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/operations/get
        - Operation resource format: https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/operations
        - Useful for chaining steps in automation and reliable handoffs in LLM flows.

    Raises:
        Exception if API polling fails, operation returns error, or times out.
    """
    logger.info(
        "[wait_cloudsql_operation] Waiting for CloudSQL operation '%s' in project '%s' "
        "(interval=%ds, timeout=%ds)", operation_id, project_id, poll_interval, timeout
    )
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")

    service = build("sqladmin", "v1beta4", cache_discovery=False)
    start_time = time.time()
    while True:
        try:
            operation = service.operations().get(
                project=project_id, operation=operation_id
            ).execute()
            status = operation.get("status")
            if status == "DONE":
                logger.info("[wait_cloudsql_operation] Operation '%s' is DONE.", operation_id)
                # Attach CloudSQL instance status if available
                target_resource = operation.get("targetId") or operation.get("targetLink")
                instance_details = None
                instance_name = None
                if "instance" in operation.get("operationType", "").lower() or (target_resource and isinstance(target_resource, str)):
                    # Try to extract instance name (from resource or metadata)
                    if "instance" in operation:
                        instance_name = operation.get("instance")
                    elif target_resource and isinstance(target_resource, str):
                        instance_name = target_resource.split("/")[-1]
                    if instance_name:
                        try:
                            instance_details = service.instances().get(project=project_id, instance=instance_name).execute()
                        except Exception as exc:
                            logger.warning("[wait_cloudsql_operation] Could not fetch instance state '%s': %s", instance_name, str(exc))
                if instance_details:
                    operation["instance_details"] = instance_details
                # Attach error details if present
                if "error" in operation and operation["error"]:
                    logger.error("[wait_cloudsql_operation] Operation '%s' finished with error: %s", operation_id, operation["error"])
                return operation
            if (time.time() - start_time) > timeout:
                logger.error("[wait_cloudsql_operation] Timed out waiting for operation '%s' (timeout=%ds)", operation_id, timeout)
                operation["error"] = {
                    "message": f"Timed out after {timeout} seconds.",
                    "code": "OPERATION_TIMEOUT"
                }
                return operation
            # More informative progress logging
            logger.info("[wait_cloudsql_operation] Operation '%s' status: %s (elapsed=%.1fs)", operation_id, status, (time.time() - start_time))
            time.sleep(poll_interval)
        except Exception as exc:
            logger.exception(
                "[wait_cloudsql_operation] Error polling operation '%s' (project '%s'): %s",
                operation_id, project_id, str(exc)
            )
            raise

@mcp.tool()
def list_cloudsql_instances(project_id: str, region: str = "-") -> dict[str, Any]:
    """
    List all CloudSQL instances for a given Google Cloud project.

    This tool returns CloudSQL instance metadata for the entire project or a specific
    region, using Application Default Credentials for authentication.

    Arguments:
        project_id (str): Google Cloud project ID.
        region (str, optional): GCP region or "-" for all regions (default: "-").

    Returns:
        dict: {
            "instances": [
                {
                    "name": str,
                    "connection_name": str,
                    "region": str,
                    "database_version": str,
                    "state": str,
                    "gce_zone": str | None,
                    "ip_addresses": list[dict[str, str]],
                    "create_time": str,
                },
                ...
            ]
        }
        If no instances are found, list will be empty.

    Example:
        result = list_cloudsql_instances(project_id="my-gcp-project")
        print(result)
        # Filter by region
        result = list_cloudsql_instances(project_id="my-gcp-project", region="us-central1")
        print(result)

    Notes:
        - Requires CloudSQL Admin/Viewer permissions and GCP credentials.
        - Uses the google-api-python-client, authorized via ADC, to access Cloud SQL Admin API.
        - See: https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/instances/list

    Raises:
        Exception if the API call fails or authentication/permission is invalid.
    """
    logger.info(
        "Listing CloudSQL instances for project '%s', region '%s'.",
        project_id, region,
    )
    if build is None:
        logger.error(
            "google-api-python-client is not installed. Please install it to use this tool."
        )
        raise ImportError("google-api-python-client package not installed")

    try:
        service = build("sqladmin", "v1beta4", cache_discovery=False)
        request = service.instances().list(project=project_id)
        response = request.execute()
        all_instances = response.get("items", [])
    except Exception as exc:
        logger.exception(
            "Failed to list CloudSQL instances for project '%s': %s",
            project_id, str(exc)
        )
        raise
    else:
        items = []
        for inst in all_instances:
            if region != "-" and inst.get("region") != region:
                continue
            try:
                # Use app_name = project_id just for fallback context; not used outside
                item = GcpCloudSQLItem.build(app_name=project_id, project_id=project_id, instance=inst)
                items.append(item.asdict())
            except Exception:
                logger.warning(
                    "Could not build CloudSQL model: %r", inst,
                    exc_info=True,
                )
        logger.info("Fetched %d CloudSQL instance records.", len(items))
        return {"instances": items}
