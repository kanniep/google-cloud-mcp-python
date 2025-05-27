"""Module for representing GCP Compute Engine Instances."""

from datetime import datetime

from google.api_core import exceptions as google_exceptions
from google.cloud import compute_v1

from app.mcp import mcp
from tools.models.error_response import ErrorResponse

# TODO: Consider inheriting from a common BaseGcpItem if one exists/is created.
# Example: from ...common.gcp_item import BaseGcpItem


class GcpComputeInstanceItem:  # Potentially: class GcpComputeInstanceItem(BaseGcpItem):
    """Class to represent a GCP Compute Engine Instance."""

    def __init__(self, instance_data: dict, project_id: str | None = None):
        """Initialize a GcpComputeInstanceItem.

        Args:
            instance_data: The instance data from the GCE API.
            project_id: The GCP project ID where the instance resides.
        """
        # If inheriting from BaseGcpItem:
        # super().__init__(item_type="compute", project_id=project_id)
        self.instance_data = instance_data
        self.project_id = project_id  # Store if not using BaseGcpItem

    @property
    def name(self) -> str:
        """Return the name of the instance."""
        return self.instance_data.get("name", "Unknown")

    @property
    def zone(self) -> str:
        """Return the zone of the instance (e.g., "us-central1-a")."""
        zone_url = self.instance_data.get("zone", "Unknown")
        return zone_url.split("/")[-1] if "/" in zone_url else zone_url

    def _get_dt(self, dt_str: str | None) -> str:
        """Format a datetime string from ISO format.

        Args:
            dt_str: The datetime string, typically in ISO 8601 format.

        Returns:
            The formatted datetime string (YYYY-MM-DD HH:MM:SS ZZZ) or "N/A".
        """
        if not dt_str:
            return "N/A"
        try:
            # GCP timestamps are typically RFC3339.
            # .replace("Z", "+00:00") helps ensure UTC 'Z' is handled.
            dt_obj = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt_obj.strftime("%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            # If parsing fails, return the original string.
            return dt_str

    def build(self) -> dict:
        """Build the instance data into a structured dictionary for display.

        Returns:
            A dictionary containing key information about the GCE instance.
        """
        # If inheriting from BaseGcpItem:
        # instance_info = super().build()
        # Else, initialize with common info:
        instance_info = {"Project ID": self.project_id or "N/A"}

        machine_type_url = self.instance_data.get("machineType", "")
        machine_type = (
            machine_type_url.split("/")[-1]
            if "/" in machine_type_url
            else machine_type_url
        )

        network_interfaces = self.instance_data.get("networkInterfaces", [])
        internal_ip = "N/A"
        external_ip = "N/A"
        if network_interfaces:
            # Primary network interface is usually the first one
            primary_nic = network_interfaces[0]
            internal_ip = primary_nic.get("networkIP", "N/A")
            access_configs = primary_nic.get("accessConfigs", [])
            if access_configs:
                # First access config usually holds the external IP
                external_ip = access_configs[0].get("natIP", "N/A")

        boot_disk_name = "N/A"
        boot_disk_size_gb = "N/A"
        disks_data = self.instance_data.get("disks", [])

        found_boot_disk = None
        if disks_data:
            # Find the disk explicitly marked as "boot: true"
            for disk_item in disks_data:
                if disk_item.get("boot"):
                    found_boot_disk = disk_item
                    break
            # If no disk is explicitly marked as boot, and there are disks,
            # assume the first disk in the list is the boot disk (common convention).
            if not found_boot_disk:  # and disks_data is not empty (already checked)
                found_boot_disk = disks_data[0]

        if found_boot_disk:
            boot_disk_name = found_boot_disk.get("deviceName", "N/A")
            # diskSizeGb is usually present in the instance resource for attached disks.
            boot_disk_size_gb = found_boot_disk.get("diskSizeGb", "N/A")

        instance_info.update(
            {
                "Name": self.name,
                "Zone": self.zone,
                "Status": self.instance_data.get("status", "UNKNOWN"),
                "Machine Type": machine_type,
                "Internal IP": internal_ip,
                "External IP": external_ip,
                "Boot Disk Name": boot_disk_name,
                "Boot Disk Size (GB)": boot_disk_size_gb,
                "Creation Timestamp": self._get_dt(
                    self.instance_data.get("creationTimestamp")
                ),
                # Consider adding other relevant fields:
                # "ID": self.instance_data.get("id"),
                # "Labels": self.instance_data.get("labels", {}),
                # "Tags": self.instance_data.get("tags", {}).get("items", []),
            }
        )
        return instance_info

    def asdict(self) -> dict:
        """Return the raw instance data as a dictionary.

        This is useful for accessing any information not exposed by `build()`.

        Returns:
            A dictionary representing the raw GCE instance data from the API.
        """
        return self.instance_data


@mcp.tool()
def list_gce_instances(
    project_id: str,
    zone: str | None = None,
) -> list[dict]:
    """
    Lists Google Compute Engine (GCE) instances in a specified project and zone.

    If no zone is specified, instances from all zones in the project will be
    listed. This function provides a summarized view of each instance, similar
    to the information one might see in the GCP console\'s instance list.

    Arguments:
        project_id (str): The Google Cloud Project ID where the instances reside.
                          Example: "my-gcp-project"
        zone (str, optional): The GCE zone to list instances from (e.g.,
                              "us-central1-a"). If None, instances from all
                              zones within the project are listed. Defaults to None.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary
                              represents a GCE instance and contains its key details
                              (Name, Zone, Status, Machine Type, IPs, etc.).
                              Returns an empty list if no instances are found or
                              in case of an API error during listing.

    Example:
        # List instances in a specific zone "us-west1-b"
        instances_in_zone = list_gce_instances(
            project_id="your-project-id",
            zone="us-west1-b"
        )
        for instance_details in instances_in_zone:
            print(f"Instance: {instance_details['Name']}, Status: {instance_details['Status']}")

        # List all instances across all zones in the project
        all_project_instances = list_gce_instances(project_id="your-project-id")
        print(f"Found {len(all_project_instances)} total instances in the project.")
        if all_project_instances:
            print(f"First instance details: {all_project_instances[0]['Name']}")


    Notes:
        - Requires the "compute.instances.list" IAM permission on the specified
          project.
        - Listing instances across all zones (when `zone` is None) can be slower
          and consume more API quota than listing from a single zone, especially
          in projects with a large number of instances.
        - The information returned is a processed subset of the full instance data.
          To get all raw data for an instance, use a "get_gce_instance" type function.

    Raises:
        google.api_core.exceptions.GoogleAPIError: If the underlying Google Cloud API
                                                   call fails for reasons such as
                                                   authentication issues, permission
                                                   denied (though often caught as
                                                   Forbidden), or other API errors.
        # Other exceptions like ConnectionError if network issues occur.
    """
    client = compute_v1.InstancesClient()
    instance_list: list[dict] = []

    try:
        if zone:
            # List instances for a specific zone
            paged_response = client.list(project=project_id, zone=zone)
            for instance_obj in paged_response:
                # Convert the instance protobuf object to a dictionary
                instance_dict = compute_v1.Instance.to_dict(instance_obj)
                item = GcpComputeInstanceItem(
                    instance_data=instance_dict, project_id=project_id
                )
                instance_list.append(item.build())
        else:
            # List instances across all zones using aggregatedList
            # The aggregated_list method returns an iterator of (zone, instances_scoped_list) tuples.
            aggregated_list_pager = client.aggregated_list(project=project_id)
            for _zone_name, instances_scoped_list_entry in aggregated_list_pager:
                if instances_scoped_list_entry.instances:
                    for instance_obj in instances_scoped_list_entry.instances:
                        # Convert the instance protobuf object to a dictionary
                        instance_dict = compute_v1.Instance.to_dict(instance_obj)
                        item = GcpComputeInstanceItem(
                            instance_data=instance_dict, project_id=project_id
                        )
                        instance_list.append(item.build())
    except google_exceptions.GoogleAPIError as e:
        return [
            {
                "error": str(e),
                "project_id": project_id,
                "zone": zone or "-",
                "instances": instance_list,
            }
        ]
    except Exception as e:
        return [
            {
                "error": str(e),
                "project_id": project_id,
                "zone": zone or "-",
                "instances": instance_list,
            }
        ]

    return instance_list


@mcp.tool()
def get_gce_instance(
    project_id: str,
    zone: str,
    instance_name: str,
) -> dict:
    """
    Retrieves detailed information for a specific Google Compute Engine (GCE) instance.

    This function fetches the complete configuration and status details for a single
    instance located in a particular project and zone. It provides a more detailed
    view than what is available in the list view.

    Arguments:
        project_id (str): The Google Cloud Project ID where the instance resides.
                          Example: "my-gcp-project"
        zone (str): The GCE zone where the instance is located (e.g., "us-central1-a").
        instance_name (str): The name of the GCE instance to retrieve.
                             Example: "my-vm-instance"

    Returns:
        Dict[str, Any]: A dictionary containing key information about the GCE instance
                        (Name, Zone, Status, Machine Type, IPs, Boot Disk details,
                        Creation Timestamp, etc.). Returns an empty dictionary if the
                        instance is not found or in case of an API error.

    Example:
        # Get details for an instance named "my-app-server" in "europe-west2-c"
        instance_details = get_gce_instance(
            project_id="your-project-id",
            zone="europe-west2-c",
            instance_name="my-app-server"
        )
        if instance_details:
            print(f"Instance found: {instance_details['Name']}, Status: {instance_details['Status']}")
        else:
            print("Instance not found or error occurred.")

    Notes:
        - Requires the "compute.instances.get" IAM permission on the specified project.
        - The zone is a mandatory argument for retrieving a specific instance.
        - The information returned is a processed subset of the full instance data,
          built using the GcpComputeInstanceItem class. The raw API response contains
          significantly more data.

    Raises:
        google.api_core.exceptions.GoogleAPIError: If the underlying Google Cloud API
                                                   call fails for reasons such as
                                                   authentication issues, permission
                                                   denied (though often caught as
                                                   Forbidden), or the instance not
                                                   being found (Caught as NotFound).
        # Other exceptions like ConnectionError if network issues occur.
    """
    client = compute_v1.InstancesClient()
    instance_dict: dict = {}

    try:
        # Get the instance resource
        instance_obj = client.get(project=project_id, zone=zone, instance=instance_name)
        # Convert the instance protobuf object to a dictionary
        instance_dict_raw = compute_v1.Instance.to_dict(instance_obj)
        # Build the structured dictionary using the helper class
        item = GcpComputeInstanceItem(
            instance_data=instance_dict_raw, project_id=project_id
        )
        instance_dict = item.build()

    except google_exceptions.NotFound:
        err = ErrorResponse(
            error=f"GCE instance '{instance_name}' not found in zone '{zone}' in project '{project_id}'.",
            detail=None,
            context={
                "project_id": project_id,
                "zone": zone,
                "instance_name": instance_name,
            },
        )
        return err.dict()
    except google_exceptions.GoogleAPIError as e:
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "project_id": project_id,
                "zone": zone,
                "instance_name": instance_name,
            },
        )
        return err.dict()
    except Exception as e:
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "project_id": project_id,
                "zone": zone,
                "instance_name": instance_name,
            },
        )
        return err.dict()

    return instance_dict


@mcp.tool()
def start_gce_instance(
    project_id: str,
    zone: str,
    instance_name: str,
    wait_for_completion: bool = True,
) -> dict:
    """
    Starts a Google Compute Engine instance.

    Args:
        project_id: The Google Cloud Project ID.
        zone: The GCE zone where the instance is located.
        instance_name: The name of the GCE instance to start.
        wait_for_completion: If True, waits for the start operation to complete.

    Returns:
        A dictionary containing the operation details. If wait_for_completion is True,
        returns the result of the wait operation.
    """
    # TODO: Replace print with proper logging using utils.logging.get_logger()
    # Optionally: Use logger instead of print
    # logger.info(
    #     f"Initiating start for GCE instance '{instance_name}' in project '{project_id}', zone '{zone}'."
    # )
    client = compute_v1.InstancesClient()
    try:
        request = compute_v1.StartInstanceRequest(
            project=project_id, zone=zone, instance=instance_name
        )
        operation = client.start(request=request)

        if not operation:
            err = ErrorResponse(
                error=f"Failed to initiate start operation for instance '{instance_name}'. No operation object returned by API client.",
                detail=None,
                context={
                    "instance_name": instance_name,
                    "project_id": project_id,
                    "zone": zone,
                    "action": "start",
                },
            )
            return err.dict()

        operation_name = operation.name

        if wait_for_completion:
            if operation_name:
                wait_status_dict = wait_gce_operation(
                    project_id=project_id, zone=zone, operation_name=operation_name
                )
                wait_status_dict["initial_action"] = "start"
                wait_status_dict["instance_name"] = instance_name
                wait_status_dict.setdefault("operation_id", operation_name)
                return wait_status_dict
            else:
                err = ErrorResponse(
                    error=f"Start operation for '{instance_name}' initiated but could not retrieve operation ID from API client response.",
                    detail=None,
                    context={
                        "instance_name": instance_name,
                        "project_id": project_id,
                        "zone": zone,
                        "action": "start",
                        "operation_details": operation.to_dict()
                        if hasattr(operation, "to_dict")
                        else {},
                    },
                )
                return err.dict()
        else:
            return operation._operation.to_dict()

    except google_exceptions.NotFound:
        err = ErrorResponse(
            error=f"GCE instance '{instance_name}' not found.",
            detail=None,
            context={
                "instance_name": instance_name,
                "project_id": project_id,
                "zone": zone,
                "action": "start",
            },
        )
        return err.dict()
    except google_exceptions.GoogleAPIError as e:
        err = ErrorResponse(
            error=f"GCP API error: {e}",
            detail=repr(e),
            context={
                "instance_name": instance_name,
                "project_id": project_id,
                "zone": zone,
                "action": "start",
                "google_api_error": str(e),
            },
        )
        return err.dict()
    except Exception as e:
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "instance_name": instance_name,
                "project_id": project_id,
                "zone": zone,
                "action": "start",
            },
        )
        return err.dict()


@mcp.tool()
def stop_gce_instance(
    project_id: str, zone: str, instance_name: str, wait_for_completion: bool = True
) -> dict:
    """
    Stops a Google Compute Engine instance.

    Args:
        project_id: The Google Cloud Project ID.
        zone: The GCE zone where the instance is located.
        instance_name: The name of the GCE instance to stop.
        wait_for_completion: If True, waits for the stop operation to complete.

    Returns:
        A dictionary containing the operation details. If wait_for_completion is True,
        returns the result of the wait operation.
    """
    # Optionally: Use logger instead of print
    client = compute_v1.InstancesClient()
    try:
        request = compute_v1.StopInstanceRequest(
            project=project_id, zone=zone, instance=instance_name
        )
        operation = client.stop(request=request)

        if not operation:
            err = ErrorResponse(
                error=f"Failed to initiate stop operation for instance '{instance_name}'. No operation details returned by API.",
                detail=None,
                context={
                    "instance_name": instance_name,
                    "project_id": project_id,
                    "zone": zone,
                    "action": "stop",
                },
            )
            return err.dict()

        operation_name = operation.name

        if wait_for_completion:
            if operation_name:
                wait_status_dict = wait_gce_operation(
                    project_id=project_id, zone=zone, operation_name=operation_name
                )
                wait_status_dict["initial_action"] = "stop"
                wait_status_dict["instance_name"] = instance_name
                wait_status_dict.setdefault("operation_id", operation_name)
                return wait_status_dict
            else:
                err = ErrorResponse(
                    error=f"Stop operation for '{instance_name}' initiated but could not retrieve operation ID from API response.",
                    detail=None,
                    context={
                        "instance_name": instance_name,
                        "project_id": project_id,
                        "zone": zone,
                        "action": "stop",
                        "operation_name": operation_name,
                    },
                )
                return err.dict()
        else:
            return compute_v1.Operation.to_dict(operation)

    except google_exceptions.NotFound:
        err = ErrorResponse(
            error=f"GCE instance '{instance_name}' not found.",
            detail=None,
            context={
                "instance_name": instance_name,
                "project_id": project_id,
                "zone": zone,
                "action": "stop",
            },
        )
        return err.dict()
    except Exception as e:
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "instance_name": instance_name,
                "project_id": project_id,
                "zone": zone,
                "action": "stop",
            },
        )
        return err.dict()


@mcp.tool()
def wait_gce_operation(
    project_id: str,
    zone: str,
    operation_name: str,
) -> dict:
    """Waits for a Google Compute Engine (GCE) zone-specific operation to complete.

    GCE operations like starting or stopping an instance are asynchronous. This
    function polls the API until the specified operation reaches a terminal state
    (e.g., DONE).

    Arguments:
        project_id (str): The Google Cloud Project ID where the operation belongs.
                          Example: "my-gcp-project"
        zone (str): The GCE zone where the operation was initiated (e.g., "us-central1-a").
        operation_name (str): The name of the operation to wait for. This name is
                              returned by functions like `start_gce_instance` or
                              `stop_gce_instance`. Example: "operation-1234567890"

    Returns:
        Dict[str, Any]: A dictionary representing the final state of the completed
                        operation. Returns an empty dictionary if the operation is
                        not found, if waiting fails, or in case of an API error.
                        The dictionary typically includes 'status', 'error' (if any),
                        and 'progress'.

    Example:
        # Assuming 'start_op' is the result from start_gce_instance(...)
        # if start_op:
        #     print(f"Waiting for operation {start_op.get('name')} to complete...")
        #     completed_op = wait_gce_operation(
        #         project_id="your-project-id",
        #         zone="us-central1-a",
        #         operation_name=start_op.get('name')
        #     )
        #     if completed_op and completed_op.get('status') == 'DONE':
        #         print("Operation completed successfully.")
        #         if completed_op.get('error'):
        #             print(f"Operation finished with error: {completed_op['error']}")
        #     else:
        #          print("Waiting for operation failed or operation did not complete.")

    Notes:
        - Requires the "compute.zoneOperations.wait" IAM permission on the specified
          project and zone.
        - This function blocks until the operation completes or an error occurs.
          It uses the API client's built-in wait method which handles polling logic.
        - The `operation_name` is crucial and must be obtained from the function
          that initiated the operation (like `start_gce_instance`).

    Raises:
        google.api_core.exceptions.NotFound: If the specified operation does not
                                            exist.
        google.api_core.exceptions.GoogleAPIError: If the underlying Google Cloud API
                                                   call fails while waiting (authentication,
                                                   permissions, network issues, etc.).
        # Other exceptions like ConnectionError if network issues occur.
    """
    # Use ZoneOperationsClient for zone-specific operations
    client = compute_v1.ZoneOperationsClient()
    operation_dict: dict = {}

    try:
        # The wait method polls the operation until it completes or times out (default 1 hour)
        operation = client.wait(project=project_id, zone=zone, operation=operation_name)
        # Convert the completed operation protobuf object to a dictionary
        operation_dict_raw = compute_v1.Operation.to_dict(operation)
        operation_dict = operation_dict_raw

    except google_exceptions.NotFound:
        err = ErrorResponse(
            error=f"GCE zone operation '{operation_name}' not found in zone '{zone}' in project '{project_id}'.",
            detail=None,
            context={
                "project_id": project_id,
                "zone": zone,
                "operation_name": operation_name,
            },
        )
        return err.dict()
    except google_exceptions.GoogleAPIError as e:
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "project_id": project_id,
                "zone": zone,
                "operation_name": operation_name,
            },
        )
        return err.dict()
    except Exception as e:
        err = ErrorResponse(
            error=str(e),
            detail=repr(e),
            context={
                "project_id": project_id,
                "zone": zone,
                "operation_name": operation_name,
            },
        )
        return err.dict()

    return operation_dict
