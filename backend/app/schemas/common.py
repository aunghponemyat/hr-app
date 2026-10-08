from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue


class RequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
