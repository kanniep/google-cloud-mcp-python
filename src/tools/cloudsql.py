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
            if dt_str.endswith("Z"):
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
            database_type=__get_db_type(version_splited[0])
            if version_splited and version_splited[0]
            else "",
            database_version=".".join(version_splited[1:])
            if len(version_splited) > 1
            else "",
            status=__get_status(instance),
            zone=instance.get("gceZone", ""),
            is_replica=instance.get("instanceType") == "READ_REPLICA_INSTANCE",
            is_ha_enabled=settings.get("availabilityType") == "REGIONAL",
            is_ssl_enabled=settings.get("ipConfiguration", {}).get(
                "sslMode",
                "ALLOW_UNENCRYPTED_AND_ENCRYPTED",
            )
            == "TRUSTED_CLIENT_CERTIFICATE_REQUIRED",
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
    logger.info(
        "Requesting start for CloudSQL instance '%s' in project '%s'.",
        instance_name,
        project_id,
    )
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")
    try:
        service = build("sqladmin", "v1beta4", cache_discovery=False)
        # Fetch the current instance config
        instance = (
            service.instances()
            .get(project=project_id, instance=instance_name)
            .execute()
        )
        # Set activationPolicy to ALWAYS to start
        instance["settings"]["activationPolicy"] = "ALWAYS"
        # Use patch to update only the activationPolicy setting
        patch_body = {"settings": {"activationPolicy": "ALWAYS"}}
        response = (
            service.instances()
            .patch(project=project_id, instance=instance_name, body=patch_body)
            .execute()
        )
        operation_id = response.get("name", "")
        logger.info(
            "Start (patch) requested for instance '%s'. Operation ID: %s",
            instance_name,
            operation_id,
        )
        return {
            "status": "STARTING",
            "instance": instance_name,
            "operation": operation_id,
        }
    except Exception as exc:
        logger.exception(
            "Failed to start CloudSQL instance '%s' for project '%s' via patch: %s",
            instance_name,
            project_id,
            str(exc),
        )
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
    logger.info(
        "Requesting stop for CloudSQL instance '%s' in project '%s'.",
        instance_name,
        project_id,
    )
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")
    try:
        service = build("sqladmin", "v1beta4", cache_discovery=False)
        # Fetch the current instance config
        instance = (
            service.instances()
            .get(project=project_id, instance=instance_name)
            .execute()
        )
        # Set activationPolicy to NEVER to stop
        instance["settings"]["activationPolicy"] = "NEVER"
        # Use patch to update only the activationPolicy setting
        patch_body = {"settings": {"activationPolicy": "NEVER"}}
        response = (
            service.instances()
            .patch(project=project_id, instance=instance_name, body=patch_body)
            .execute()
        )
        operation_id = response.get("name", "")
        logger.info(
            "Stop (patch) requested for instance '%s'. Operation ID: %s",
            instance_name,
            operation_id,
        )
        return {
            "status": "STOPPING",
            "instance": instance_name,
            "operation": operation_id,
        }
    except Exception as exc:
        logger.exception(
            "Failed to stop CloudSQL instance '%s' for project '%s' via patch: %s",
            instance_name,
            project_id,
            str(exc),
        )
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
        item = GcpCloudSQLItem.build(
            app_name=project_id, project_id=project_id, instance=response
        )
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


def _wait_cloudsql_operation_single(
    project_id: str,
    operation_id: str,
    poll_interval: int = 2,
    timeout: int = 60,
    logger_obj=None,
) -> dict[str, Any]:
    """
    Helper: Poll a Cloud SQL operation for a short period.
    Returns the most recent operation resource (status: DONE, or after timeout).
    """
    log = logger_obj or logger
    if build is None:
        log.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")
    service = build("sqladmin", "v1beta4", cache_discovery=False)
    start_time = time.time()
    while True:
        try:
            operation = (
                service.operations()
                .get(project=project_id, operation=operation_id)
                .execute()
            )
            status = operation.get("status")
            if status == "DONE":
                log.info(
                    "[_wait_cloudsql_operation_single] Operation '%s' is DONE.",
                    operation_id,
                )
                return operation
            if (time.time() - start_time) > timeout:
                log.warning(
                    "[_wait_cloudsql_operation_single] Timeout reached (%ss) for operation '%s'.",
                    timeout,
                    operation_id,
                )
                return operation
            time.sleep(poll_interval)
        except Exception as exc:
            log.error(
                "[_wait_cloudsql_operation_single] Error polling operation '%s' (project '%s'): %s",
                operation_id,
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
    Robustly poll a Cloud SQL Admin API operation until DONE using short waits,
    with retries to overcome context/request timeouts.

    Intended for use in automation or agent environments where a server or platform
    may enforce hard limits on request duration.

    Arguments:
        project_id (str): Google Cloud project ID where the operation resides.
        operation_id (str): The GCP operation ID returned by an async request.
        poll_interval (int, optional): Seconds between polls (default: 2).
        timeout (int, optional): Maximum seconds to wait in total (default: 300).

    Returns:
        dict: The final operation resource as returned by the API, with attached instance state.
            - If successful, {"status": "DONE", ...} and "instance_details" key if found.
            - If timeout/error, includes error details.

    Quick Reference:
        # Wait up to 5 min using repeated 60s checks:
        result = wait_cloudsql_operation("project", "opid", timeout=300)

    Notes:
        - Designed to safely work across platforms with strict per-request limits.
        - Will always check for "DONE", and attaches relevant instance information.
    """
    logger.info(
        "[wait_cloudsql_operation] Robust poll for operation '%s' (project '%s'), interval=%s, timeout=%s",
        operation_id,
        project_id,
        poll_interval,
        timeout,
    )
    if build is None:
        logger.error("google-api-python-client package not installed")
        raise ImportError("google-api-python-client package not installed")
    per_call_timeout = min(60, timeout)
    elapsed = 0
    final_operation = None

    while elapsed < timeout:
        remaining = timeout - elapsed
        single_wait = min(per_call_timeout, remaining)
        operation = _wait_cloudsql_operation_single(
            project_id=project_id,
            operation_id=operation_id,
            poll_interval=poll_interval,
            timeout=single_wait,
            logger_obj=logger,
        )
        status = operation.get("status")
        if status == "DONE":
            logger.info(
                "[wait_cloudsql_operation] Operation '%s' is DONE.", operation_id
            )
            # Attach instance details if possible
            service = build("sqladmin", "v1beta4", cache_discovery=False)
            target_resource = operation.get("targetId") or operation.get("targetLink")
            instance_details = None
            instance_name = None
            if "instance" in (operation.get("operationType", "")).lower() or (
                target_resource and isinstance(target_resource, str)
            ):
                if "instance" in operation:
                    instance_name = operation.get("instance")
                elif target_resource and isinstance(target_resource, str):
                    instance_name = target_resource.split("/")[-1]
                if instance_name:
                    try:
                        instance_details = (
                            service.instances()
                            .get(project=project_id, instance=instance_name)
                            .execute()
                        )
                    except Exception as exc:
                        logger.warning(
                            "[wait_cloudsql_operation] Could not fetch instance state '%s': %s",
                            instance_name,
                            str(exc),
                        )
            if instance_details:
                operation["instance_details"] = instance_details
            return operation
        elapsed += single_wait
        final_operation = operation
        logger.info(
            "[wait_cloudsql_operation] Partial wait: operation '%s' not done after %ss (total elapsed: %ss)",
            operation_id,
            single_wait,
            elapsed,
        )
    # Attach error info if completely timed out
    if final_operation is not None:
        final_operation["error"] = {
            "message": f"Timed out after {timeout} seconds.",
            "code": "OPERATION_TIMEOUT",
        }
    return final_operation or {
        "error": {"message": "Unknown error waiting for operation", "code": "UNKNOWN"}
    }


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
        project_id,
        region,
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
            project_id,
            str(exc),
        )
        raise
    else:
        items = []
        for inst in all_instances:
            if region != "-" and inst.get("region") != region:
                continue
            try:
                # Use app_name = project_id just for fallback context; not used outside
                item = GcpCloudSQLItem.build(
                    app_name=project_id, project_id=project_id, instance=inst
                )
                items.append(item.asdict())
            except Exception:
                logger.warning(
                    "Could not build CloudSQL model: %r",
                    inst,
                    exc_info=True,
                )
        logger.info("Fetched %d CloudSQL instance records.", len(items))
        return {"instances": items}
