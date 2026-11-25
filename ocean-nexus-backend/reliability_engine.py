# reliability_engine.py

def assess_argo_reliability(
    profile_count,
    qc1_count,
    adjusted_count,
    delayed_mode_count,
    pressure_error_count,
    temporal_coverage,
    spatial_coverage
):
    """
    Assess whether ARGO observations are sufficient
    for generating a scientific interpretation.
    """

    qc_pass_rate = (
        qc1_count / profile_count
        if profile_count > 0 else 0
    )

    adjusted_pass_rate = (
        adjusted_count / profile_count
        if profile_count > 0 else 0
    )

    delayed_mode_pass_rate = (
        delayed_mode_count / profile_count
        if profile_count > 0 else 0
    )

    pressure_pass_rate = (
        pressure_error_count / profile_count
        if profile_count > 0 else 0
    )

    # Minimum evidence threshold
    MIN_PROFILES = 50

    reasons = []

    if profile_count < MIN_PROFILES:
        reasons.append(
            f"Only {profile_count} profiles are available. "
            f"Minimum required: {MIN_PROFILES}."
        )

    if qc_pass_rate < 0.80:
        reasons.append(
            f"QC-passing observations are only "
            f"{qc_pass_rate * 100:.1f}%."
        )

    if adjusted_pass_rate < 0.80:
        reasons.append(
            f"Adjusted observations are only "
            f"{adjusted_pass_rate * 100:.1f}%."
        )

    if delayed_mode_pass_rate < 0.80:
        reasons.append(
            f"Delayed-mode coverage is only "
            f"{delayed_mode_pass_rate * 100:.1f}%."
        )

    if pressure_pass_rate < 0.80:
        reasons.append(
            "Some observations exceed the accepted "
            "pressure-error threshold."
        )

    if temporal_coverage == "SPARSE":
        reasons.append(
            "Temporal coverage is too sparse "
            "to confidently identify a trend."
        )

    if spatial_coverage == "SPARSE":
        reasons.append(
            "Spatial coverage is too sparse "
            "for regional interpretation."
        )

    reliable = len(reasons) == 0

    if reliable:
        confidence = "HIGH"
        decision = "ANALYZE"
        message = (
            "Sufficient evidence available. "
            "Scientific interpretation can be generated."
        )
    else:
        confidence = "LOW"
        decision = "REFUSE"
        message = (
            "Insufficient evidence. "
            "Ocean Nexus AI will not report a trend."
        )

    return {
        "reliable": reliable,
        "decision": decision,
        "confidence": confidence,
        "profile_count": profile_count,
        "qc_pass_rate": round(qc_pass_rate * 100, 2),
        "adjusted_pass_rate": round(adjusted_pass_rate * 100, 2),
        "delayed_mode_pass_rate": round(
            delayed_mode_pass_rate * 100, 2
        ),
        "pressure_pass_rate": round(
            pressure_pass_rate * 100, 2
        ),
        "reasons": reasons,
        "message": message
    }