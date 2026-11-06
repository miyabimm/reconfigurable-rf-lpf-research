"""Value-free circuit structure and electrical connection-role evidence."""
from .circuit_layout import InductorTree, CapacitorPlacement
from .definition import CircuitDefinition
from .role_audit import (
    ConnectionRoleEvidence, ConnectionRoleAudit, audit_variable_connection_roles,
)
