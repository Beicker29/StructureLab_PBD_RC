"""Custom exceptions for StructureLab_PBD_RC."""


class StructureLabError(Exception):
    """Base exception for project-specific errors."""


class ConfigError(StructureLabError):
    """Raised when configuration files are missing or invalid."""


class ModelNotImplementedError(StructureLabError, NotImplementedError):
    """Raised by model stubs that intentionally do not compute yet."""


class RegistryError(StructureLabError):
    """Raised when the model registry receives invalid operations."""


class ContractError(StructureLabError, ValueError):
    """Raised when a versioned V2 contract is invalid."""


class SchemaVersionError(ContractError):
    """Raised when a contract schema version is unsupported."""


class DependencyError(ContractError):
    """Raised when a declared artifact or module dependency is invalid."""


class UnitBoundaryError(ContractError):
    """Raised when units, signs, or reference systems are incompatible."""


class PublicationError(StructureLabError):
    """Base error for isolated V2 publication."""


class PublicationCollisionError(PublicationError):
    """Raised when a V2 run identity is already published."""


class PublicationValidationError(PublicationError):
    """Raised when staged V2 artifacts are not safe to publish."""


class WorkflowError(StructureLabError):
    """Base error for V2 workflow planning and sequential execution."""


class WorkflowCycleError(WorkflowError):
    """Raised when the module dependency graph contains a cycle."""


class HandlerRegistrationError(WorkflowError):
    """Raised when the V2 handler registry receives an invalid operation."""


class MaterialDomainError(StructureLabError, ValueError):
    """Raised when a material is evaluated outside its supported domain."""

