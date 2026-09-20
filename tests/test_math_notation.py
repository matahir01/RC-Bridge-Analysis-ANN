from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate

from rc_bridge.application.math_notation import (
    MathFormulaFlowable,
    fraction,
    identifier,
    mathml,
    number,
    operator,
    row,
    sqrt,
    sub,
    sup,
)


def _representative_expression():
    return row(
        sub(identifier("k"), "ww"),
        operator("="),
        fraction(
            row(number("12"), identifier("E"), sub(identifier("I"), "y")),
            sup(identifier("L"), 3),
        ),
        operator("+"),
        sqrt(
            fraction(
                number("200"),
                identifier("d"),
            )
        ),
    )


def test_mathml_uses_native_fraction_radical_and_scripts() -> None:
    markup = mathml(_representative_expression())

    assert "<math" in markup
    assert "<mfrac>" in markup
    assert "<msqrt>" in markup
    assert "<msub>" in markup
    assert "<msup>" in markup
    assert "sqrt(" not in markup


def test_pdf_math_flowable_fits_available_width_and_builds(tmp_path) -> None:
    formula = MathFormulaFlowable(
        _representative_expression(),
        font_size=10.0,
    )
    width, height = formula.wrap(90.0, 500.0)

    assert width <= 90.0
    assert height > 0.0

    output = tmp_path / "math_formula.pdf"
    document = SimpleDocTemplate(str(output), pagesize=A4)
    document.build([formula])

    data = output.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 1000
