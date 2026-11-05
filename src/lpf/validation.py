"""Third-formulation circuit checks and independent connection audits."""
from collections import Counter

import numpy as np
from .constraint_versions import load_constraint


def _checked_solve(matrix,rhs,label):
    condition=float(np.linalg.cond(matrix))
    if not np.isfinite(condition) or condition>1e13:
        raise ValueError(f"{label} is singular or ill-conditioned (cond={condition:.3g})")
    result=np.linalg.solve(matrix,rhs)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{label} returned non-finite values")
    return result,condition


def _edge_counts(branches):
    return Counter((branch.a,branch.b) for branch in branches)


def validate_connection_map(params, *, expected_inductor_edges=None,
                            expected_capacitor_edges=None):
    """Compare solver branches to an independently retained source topology map."""
    if expected_inductor_edges is not None:
        expected=Counter(tuple(edge) for edge in expected_inductor_edges)
        if _edge_counts(params.get("inductors",()))!=expected:
            raise ValueError("Inductor connection map differs from source topology")
    if expected_capacitor_edges is not None:
        expected=Counter(tuple(edge) for edge in expected_capacitor_edges)
        if _edge_counts(params.get("capacitors",()))!=expected:
            raise ValueError("Capacitor connection map differs from source topology")
    return True


def validate_inductor_coupling(types,values,coupling,physical_order=None,*,
                               nominal=True,resolved_policy=None):
    """Enforce RF-F001 nominal or explicit weak-coupling sensitivity rules.

    Nonadjacent chip pairs have nominal k=0. Only nominal=False permits
    |k|<=0.1 for a separate weak-coupling sensitivity calculation.
    """
    policy = load_constraint() if resolved_policy is None else resolved_policy
    limits = policy["coupling_limits"]
    k=np.asarray(coupling,float);l=np.asarray(values,float);n=len(types)
    if type(nominal) is not bool:raise ValueError('nominal must be a boolean')
    if (l.shape!=(n,) or np.any(~np.isfinite(l)) or np.any(l<=0)
            or k.shape!=(n,n) or np.any(~np.isfinite(k))
            or not np.allclose(k,k.T,atol=1e-12,rtol=0)
            or not np.allclose(np.diag(k),1,atol=1e-12,rtol=0)):
        raise ValueError("Invalid coupling or inductor values")
    if n==0:
        return {"min_inductance_eigenvalue":None,
                "max_inductance_eigenvalue":None,
                "inductance_condition_number":None}
    chips=[i for i,t in enumerate(types)
           if t in ("LQP01","LQP02","LQP02HV","LQP02HQ","LQW04")]
    pcbs=[i for i,t in enumerate(types) if t=="PCB_L"]
    if len(pcbs)>policy["components"]["PCB_L"]["max_count_principle"]:
        raise ValueError("PCB count exceeds three")
    pcb_max=policy['components']['PCB_L']['bounds']['max']
    if any(l[i]>pcb_max*1e-9+1e-21 for i in pcbs):
        raise ValueError("PCB inductance limit exceeded")
    order=chips if physical_order is None else list(physical_order)
    if sorted(order)!=sorted(chips):raise ValueError("Physical chip order is invalid")
    adjacent={frozenset((a,b)) for a,b in zip(order,order[1:])}
    for i in range(n):
        for j in range(i+1,n):
            pair=frozenset((i,j));value=abs(k[i,j])
            if i in chips and j in chips:
                limit=(limits["chip_chip_strong_adjacent_abs_k_max"] if pair in adjacent
                       else (0.0 if nominal else limits["chip_chip_nonstrong_abs_k_max"]))
            elif (i in chips and j in pcbs) or (j in chips and i in pcbs):
                limit=limits["chip_pcb_abs_k_max"]
            elif i in pcbs and j in pcbs:
                limit=limits["pcb_pcb_abs_k_max_default"]
            else:
                limit=0.0
            if value>limit+1e-12:
                raise ValueError("Strong chip coupling is forbidden for physically nonadjacent inductors")
    mutual=k*np.sqrt(np.outer(l,l))
    eigenvalues=np.linalg.eigvalsh(mutual)
    if eigenvalues.min()<=eigenvalues.max()*1e-12:
        raise ValueError("Full inductance matrix is non-positive-definite or ill-conditioned")
    return {"min_inductance_eigenvalue":float(eigenvalues.min()),
            "max_inductance_eigenvalue":float(eigenvalues.max()),
            "inductance_condition_number":float(eigenvalues.max()/eigenvalues.min())}


def solve_branch_current(f_hz,n_nodes,source_node,load_node,inductors=(),
                         capacitors=(),coupling=None,source_voltage=1.0,
                         source_ohms=50.0,load_ohms=60-40j):
    """Independent all-branch-current MNA, including finite-Q capacitor currents."""
    if (not np.isfinite(f_hz) or f_hz<=0 or type(n_nodes) is not int or n_nodes<1
            or not 1<=source_node<=n_nodes or not 1<=load_node<=n_nodes
            or not np.isfinite(source_ohms) or source_ohms<=0
            or not np.isfinite(load_ohms.real) or not np.isfinite(load_ohms.imag)
            or load_ohms.real<=0
            or not np.isfinite(source_voltage.real) or not np.isfinite(source_voltage.imag)
            or abs(source_voltage)==0):
        raise ValueError("Invalid circuit inputs")
    inductors=tuple(inductors);capacitors=tuple(capacitors);nl=len(inductors)
    w=2*np.pi*f_hz
    l=np.asarray([x.value for x in inductors],float)
    ql=np.asarray([x.q for x in inductors],float)
    if np.any(~np.isfinite(l)) or np.any(l<=0) or np.any(~np.isfinite(ql)) or np.any(ql<=0):
        raise ValueError("Invalid inductor values or Q")
    k=np.eye(nl) if coupling is None else np.asarray(coupling,float)
    if (k.shape!=(nl,nl) or np.any(~np.isfinite(k))
            or not np.allclose(k,k.T,atol=1e-12,rtol=0)
            or not np.allclose(np.diag(k),1,atol=1e-12,rtol=0)):
        raise ValueError("Invalid coupling matrix")
    mutual=k*np.sqrt(np.outer(l,l)) if nl else np.zeros((0,0))
    if nl:
        eig=np.linalg.eigvalsh(mutual)
        if eig.min()<=eig.max()*1e-12:
            raise ValueError("Full inductance matrix is non-positive-definite or ill-conditioned")
        z_l=np.diag(w*l/ql)+1j*w*mutual
    else:z_l=np.zeros((0,0),complex)
    cap_active=[];cap_indices=[];cap_impedances=[]
    for index,cap in enumerate(capacitors):
        if (type(cap.a) is not int or type(cap.b) is not int or cap.a==cap.b
                or min(cap.a,cap.b)<0 or max(cap.a,cap.b)>n_nodes
                or not np.isfinite(cap.value) or cap.value<0
                or not np.isfinite(cap.q) or cap.q<=0):
            raise ValueError("Invalid capacitor")
        if cap.value>0:
            cap_active.append(cap);cap_indices.append(index)
            cap_impedances.append((1/cap.q-1j)/(w*cap.value))
    branches=inductors+tuple(cap_active);nb=len(branches)
    bmat=np.zeros((n_nodes,nb),complex)
    for j,branch in enumerate(branches):
        if (type(branch.a) is not int or type(branch.b) is not int
                or branch.a==branch.b or min(branch.a,branch.b)<0
                or max(branch.a,branch.b)>n_nodes):
            raise ValueError("Invalid branch endpoints")
        if branch.a:bmat[branch.a-1,j]+=1
        if branch.b:bmat[branch.b-1,j]-=1
    y=np.zeros((n_nodes,n_nodes),complex)
    y[source_node-1,source_node-1]+=1/source_ohms
    y[load_node-1,load_node-1]+=1/load_ohms
    z=np.zeros((nb,nb),complex)
    if nl:z[:nl,:nl]=z_l
    for j,impedance in enumerate(cap_impedances,nl):z[j,j]=impedance
    a=np.block([[y,bmat],[-bmat.T,z]])
    rhs=np.zeros(n_nodes+nb,complex);rhs[source_node-1]=source_voltage/source_ohms
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(rhs)):
        raise ValueError("Branch-current MNA assembled a non-finite system")
    raw_condition=float(np.linalg.cond(a))

    # The raw system mixes KCL rows (A), KVL rows (V), node-voltage unknowns
    # (V), and branch-current unknowns (A). A nearly open capacitor therefore
    # contributes a huge impedance in one diagonal entry and makes cond(A)
    # depend overwhelmingly on units, even though its current is negligible.
    # Apply the exact variable/equation transform A_s = R A D, b_s = R b:
    # node voltages scale by V0, branch currents by V0/|Z_jj|, KCL rows by
    # 1/I0, and KVL rows by 1/V0. This is algebraically equivalent, not a
    # change to the circuit or the ill-conditioning acceptance threshold.
    voltage_scale=abs(source_voltage)
    current_scale=voltage_scale/source_ohms
    branch_impedance_scale=np.abs(np.diag(z))
    if (not np.all(np.isfinite(branch_impedance_scale))
            or np.any(branch_impedance_scale<=0)):
        raise ValueError("Branch-current MNA has an invalid impedance scaling")
    column_scale=np.concatenate((
        np.full(n_nodes,voltage_scale),voltage_scale/branch_impedance_scale))
    row_scale=np.concatenate((
        np.full(n_nodes,1/current_scale),np.full(nb,1/voltage_scale)))
    scaled_a=(row_scale[:,None]*a)*column_scale[None,:]
    scaled_rhs=row_scale*rhs
    scaled_solution,condition=_checked_solve(scaled_a,scaled_rhs,"Branch-current MNA")
    solution=column_scale*scaled_solution
    voltage=solution[:n_nodes];currents=solution[n_nodes:]
    i_l=currents[:nl];i_c=np.zeros(len(capacitors),complex)
    for offset,index in enumerate(cap_indices):i_c[index]=currents[nl+offset]
    p_available=float(abs(source_voltage)**2/(4*source_ohms))
    p_load=float(abs(voltage[load_node-1])**2*(1/load_ohms).real)
    p_reflected=float(abs(source_voltage-2*voltage[source_node-1])**2/(4*source_ohms))
    p_inductor=float(np.sum(w*l/ql*np.abs(i_l)**2))
    p_cap=float(sum(abs(i_c[i])**2/(w*c.value*c.q)
                    for i,c in enumerate(capacitors) if c.value>0))
    residual=p_available-p_load-p_reflected-p_inductor-p_cap
    if abs(residual)>max(1e-12,p_available*1e-9):
        raise ValueError(f"Branch-current MNA power conservation failed (residual={residual:.3g} W)")
    return {"voltage":voltage,"inductor_current":i_l,"capacitor_current":i_c,
            "gain":p_load/p_available,"p_available":p_available,"p_load":p_load,
            "p_reflected":p_reflected,"p_inductor":p_inductor,"p_capacitor":p_cap,
            "power_residual":residual,"condition_number":condition,
            "raw_condition_number":raw_condition if np.isfinite(raw_condition) else None,
            "min_inductance_eigenvalue":float(np.linalg.eigvalsh(mutual).min()) if nl else None}


def validate_circuit(params,frequencies_hz,*,expected_inductor_edges=None,
                     expected_capacitor_edges=None,inductor_types=None,
                     physical_order=None,gain_atol=1e-10,nominal=True,
                     resolved_policy=None):
    """Compare main MNA, nodal elimination, and all-branch-current MNA per Hz."""
    from .circuit import solve
    from .independent import solve_state
    validate_connection_map(params,expected_inductor_edges=expected_inductor_edges,
                            expected_capacitor_edges=expected_capacitor_edges)
    lmat=np.asarray(params.get("coupling") if params.get("coupling") is not None
                    else np.eye(len(params.get("inductors",()))),float)
    lv=[x.value for x in params.get("inductors",())]
    eigen={"min_inductance_eigenvalue":None}
    if inductor_types:
        eigen=validate_inductor_coupling(inductor_types,lv,lmat,physical_order,
                                         nominal=nominal,resolved_policy=resolved_policy)
    discrepancies=[];residuals=[];condition_numbers=[];raw_branch_condition_numbers=[]
    for f_hz in frequencies_hz:
        primary=solve(f_hz,**params)
        nodal=solve_state(f_hz,**params)
        branch=solve_branch_current(f_hz,**params)
        gains=(primary["gain"],nodal["gain"],branch["gain"])
        discrepancy=max(abs(gains[0]-gains[1]),abs(gains[0]-gains[2]),abs(gains[1]-gains[2]))
        if discrepancy>gain_atol:
            raise ValueError(f"Independent gain mismatch at {f_hz:g} Hz: {discrepancy:.3g}")
        discrepancies.append(discrepancy)
        residuals.extend(abs(result["power_residual"]) for result in (primary,nodal,branch))
        condition_numbers.append(primary.get("mna_condition_number",0))
        condition_numbers.extend((nodal["nodal_condition_number"],branch["condition_number"]))
        if branch["raw_condition_number"] is not None:
            raw_branch_condition_numbers.append(branch["raw_condition_number"])
    return {"frequencies_hz":list(map(float,frequencies_hz)),
            "frequency_count":len(discrepancies),
            "max_gain_discrepancy":max(discrepancies,default=0.0),
            "max_power_residual_w":max(residuals,default=0.0),
            "max_condition_number":max(condition_numbers,default=0.0),
            "max_raw_branch_condition_number":max(raw_branch_condition_numbers,default=0.0),
            **eigen}
