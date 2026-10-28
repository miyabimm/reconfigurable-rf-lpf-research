"""Conservative candidate-audit starting point for Stage 2.

This deliberately does not accept caller-supplied evidence flags. Evidence
binding and dense/physical/owner gates require further review; until then this
function cannot certify or promote any candidate.
"""


def audit_candidate(circuit, vector):
    """Re-run the component and L-tree role checks; leave other checks not run.

    Exceptions from the policy adapter are propagated rather than converted to
    a passing report. A supported electrical role is not a physical proof.
    """
    component = circuit.validate_components(vector)
    roles = circuit.connection_role_audit()
    role_complete = roles["all_declared_roles_supported_by_l_tree"] is True
    component_pass = component.get("component_policy_pass") is True
    blockers = []
    if not component_pass:
        blockers.append("component_policy_failed")
    if not role_complete:
        blockers.append("declared_role_not_proven_by_l_tree")
    # Retain adapter-provided blockers even if new ones are added later.
    for blocker in component.get("promotion_blockers", ()):
        if blocker not in blockers:
            blockers.append(blocker)
    for blocker in ("forward_sampled_not_checked", "independent_mna_not_checked",
                     "dense_rf_not_checked", "local_extrema_not_checked",
                     "optimization_convergence_not_checked",
                     "physical_validation_not_checked", "owner_approval_not_recorded"):
        if blocker not in blockers:
            blockers.append(blocker)
    return {
        "constraint_id": circuit.policy_id,
        "constraint_fingerprint": circuit.policy_fingerprint,
        "component_policy_pass": component_pass,
        "component_policy": component,
        "connection_role_evidence_complete": role_complete,
        "connection_role_audit": roles,
        "forward_sampled_checked": False,
        "independent_mna_checked": False,
        "rf_dense_evaluation_completed": False,
        "local_extrema_checked": False,
        "optimization_converged": None,
        "physical_validation_checked": False,
        "owner_approval_recorded": False,
        "eligible_for_owner_review": False,
        "rf_compliance_certified": False,
        "candidate_promotion_blocked": True,
        "promotion_blockers": tuple(blockers),
    }
