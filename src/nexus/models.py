from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformInfo(BaseModel):
    name: str
    version: str
    python_executable: str | None = None


class LayerConfig(BaseModel):
    package: str
    project_path: str
    cli_module: str
    config_path: str
    responsibility: str


class FlowConfig(BaseModel):
    description: str
    sequence: list[str] = Field(default_factory=list)


class NexusConfig(BaseModel):
    platform: PlatformInfo
    layers: dict[str, LayerConfig]
    flows: dict[str, FlowConfig] = Field(default_factory=dict)


class LayerStatus(BaseModel):
    name: str
    project_exists: bool
    pyproject_exists: bool
    config_exists: bool
    readme_exists: bool
    cli_module: str
    ready: bool
