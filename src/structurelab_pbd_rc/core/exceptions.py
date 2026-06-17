"""Custom exceptions for StructureLab_PBD_RC."""


class StructureLabError(Exception):
    """Base exception for project-specific errors."""


class ConfigError(StructureLabError):
    """Raised when configuration files are missing or invalid."""


class ModelNotImplementedError(StructureLabError, NotImplementedError):
    """Raised by model stubs that intentionally do not compute yet."""


class RegistryError(StructureLabError):
    """Raised when the model registry receives invalid operations."""

