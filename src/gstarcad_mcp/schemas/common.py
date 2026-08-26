"""Common strict models: base config, points, bounds."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class Point3(StrictModel):
    x: float = Field(description="X coordinate in drawing units")
    y: float = Field(description="Y coordinate in drawing units")
    z: float = Field(default=0.0, description="Z coordinate in drawing units")

    @model_validator(mode="before")
    @classmethod
    def _from_sequence(cls, value):
        # Accept [x, y] / [x, y, z] arrays alongside {x, y, z} objects.
        if isinstance(value, (list, tuple)):
            if len(value) == 2:
                return {"x": value[0], "y": value[1]}
            if len(value) == 3:
                return {"x": value[0], "y": value[1], "z": value[2]}
            raise ValueError("point must have 2 or 3 coordinates")
        return value

    @field_validator("x", "y", "z")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coordinate must be finite")
        return value

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def as_array(self) -> list[float]:
        return [self.x, self.y, self.z]


class Bounds3(StrictModel):
    minimum: Point3
    maximum: Point3
