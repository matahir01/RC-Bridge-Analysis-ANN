from rc_bridge.export.external_results import validate_external_result_coverage


def _template() -> str:
    return (
        "result_type,object_id,span_index,position_m,component,value,unit\n"
        "support_reaction,1,,,FZ,,kN\n"
        "node_displacement,1,,,DZ,,m\n"
        "member_end_force,10,,I,V_VERTICAL,,kN\n"
        "member_end_force,10,,I,M_VERTICAL,,kNm\n"
    )


def test_external_result_coverage_reports_complete_return_set() -> None:
    external = (
        "result_type,object_id,span_index,position_m,component,value,unit\n"
        "support_reaction,1,,,FZ,100,kN\n"
        "node_displacement,1,,,DZ,-0.012,m\n"
        "member_end_force,10,,I,V_VERTICAL,45,kN\n"
        "member_end_force,10,,I,M_VERTICAL,180,kNm\n"
    )
    report = validate_external_result_coverage(template_csv=_template(), external_csv=external)

    assert report.complete
    assert report.requested_count == 4
    assert report.provided_count == 4
    assert report.matched_count == 4
    assert report.missing_keys == ()
    assert report.unexpected_keys == ()


def test_external_result_coverage_identifies_missing_and_unexpected_rows() -> None:
    external = (
        "result_type,object_id,span_index,position_m,component,value,unit\n"
        "support_reaction,1,,,FZ,100,kN\n"
        "node_displacement,1,,,DZ,-0.012,m\n"
        "member_end_force,99,,J,T,5,kNm\n"
    )
    report = validate_external_result_coverage(template_csv=_template(), external_csv=external)

    assert not report.complete
    assert report.requested_count == 4
    assert report.provided_count == 3
    assert report.matched_count == 2
    assert len(report.missing_keys) == 2
    assert any("V_VERTICAL" in key for key in report.missing_keys)
    assert any("M_VERTICAL" in key for key in report.missing_keys)
    assert report.unexpected_keys == (
        "member_end_force|object=99|span=|position=J|T|kNm",
    )
