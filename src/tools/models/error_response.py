from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error message string")
    detail: str | None = Field(
        None,
        description="Optional detailed error information (stacktrace, exception repr, etc.)",
    )
    context: dict[str, Any] | None = Field(
        None,
        description="Optional extra context such as project_id, resource name, etc.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Permission denied while starting instance.",
                "detail": "google.api_core.exceptions.Forbidden: 403 Permission denied",
                "context": {"project_id": "gcp-demo", "instance_name": "my-instance"},
            }
        }
