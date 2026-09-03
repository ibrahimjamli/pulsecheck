"""Request and response bodies. Kept separate from the ORM models so the
wire format can change without a database migration."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    expected_status: int = Field(default=200, ge=100, le=599)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    expected_status: int
    created_at: datetime


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    status_code: int | None
    latency_ms: float | None
    up: bool
    error: str | None
    checked_at: datetime


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
