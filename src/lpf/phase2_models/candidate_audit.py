"""Conservative candidate-audit starting point for Stage 2.

This deliberately does not accept caller-supplied evidence flags. Evidence
binding and dense/physical/owner gates require further review; until then this
function cannot certify or promote any candidate.
"""


def audit_candidate(circuit, vector, *, limited_points_per_interval=None, prior_evidence=None):
    """Re-run component/role checks and optionally a limited canonical grid.

    Exceptions from the policy adapter are propagated rather than converted to
    a passing report. A supported electrical role is not a physical proof.
    A prior record is compared only after a complete recomputation; it cannot
    supply a PASS by itself. No grid is a certification.
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
    evidence = None
    state = "not_checked"
    reason = None
    if limited_points_per_interval is not None or prior_evidence is not None:
        # Never trust a prior record: compare it to a new calculation.
        from .limited_candidate_evidence import (EvidenceFailure, compare_recomputed_evidence,
                                                  recompute_limited_evidence)
        import subprocess
        try:
            evidence = recompute_limited_evidence(circuit, vector, limited_points_per_interval)
            if prior_evidence is not None:
                compare_recomputed_evidence(prior_evidence, evidence)
            state = "passed_limited"
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            evidence = None
            state = "failed"
            reason = (exc.reason if isinstance(exc, EvidenceFailure)
                      else getattr(exc, "code", "limited_evidence_failed"))
            blockers.append("limited_evidence_" + reason)
    threshold_failures = []
    if evidence is not None:
        for region, group in evidence["threshold_observations"].items():
            limits = {"nominal": group} if region in ("UL", "DL") else group
            for limit, observation in limits.items():
                if observation["status"] == "failed":
                    code = f"rf_sampled_{region.lower()}_{limit}_failed"
                    threshold_failures.append({"reason": code, "region": region,
                                               "limit": limit, "observation": observation})
                    if code not in blockers:
                        blockers.append(code)
    return {
        "constraint_id": circuit.policy_id,
        "constraint_fingerprint": circuit.policy_fingerprint,
        "component_policy_pass": component_pass,
        "component_policy": component,
        "connection_role_evidence_complete": role_complete,
        "connection_role_audit": roles,
        "forward_sampled_checked": state == "passed_limited",
        "independent_mna_checked": state == "passed_limited",
        "forward_sampled_state": state,
        "independent_mna_state": state,
        "power_accounting_state": state,
        "limited_evidence_failure_reason": reason,
        "limited_evidence": evidence,
        "rf_threshold_state": "not_checked" if evidence is None else (
            "failed" if threshold_failures else "sampled_numeric_observation"),
        "rf_threshold_failures": threshold_failures,
        "dense_rf_state": "not_checked",
        "local_extrema_state": "not_checked",
        "optimization_state": "not_checked",
        "physical_validation_state": "not_checked",
        "owner_approval_state": "not_checked",
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
