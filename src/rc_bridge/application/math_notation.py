from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Literal

from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable


MathKind = Literal[
    "row",
    "identifier",
    "number",
    "operator",
    "text",
    "fraction",
    "sqrt",
    "sub",
    "sup",
    "subsup",
]


@dataclass(frozen=True)
class MathExpr:
    """Small structured-math tree shared by HTML and PDF calculation reports.

    The report layer intentionally supports only the notation needed by the
    deterministic bridge calculations: rows, fractions, square roots,
    subscripts/superscripts and ordinary mathematical symbols. Engineering logic
    remains in the analysis/design engine; this tree controls presentation only.
    """

    kind: MathKind
    text: str = ""
    children: tuple[MathExpr, ...] = ()

    def __post_init__(self) -> None:
        leaf_kinds = {"identifier", "number", "operator", "text"}
        if self.kind in leaf_kinds:
            if not self.text:
                raise ValueError("Math leaf nodes require text.")
            if self.children:
                raise ValueError("Math leaf nodes cannot contain children.")
        elif self.kind == "row":
            if not self.children:
                raise ValueError("Math rows require at least one child.")
        elif self.kind in {"fraction", "sub", "sup"}:
            if len(self.children) != 2:
                raise ValueError(f"{self.kind} math nodes require two children.")
        elif self.kind == "subsup":
            if len(self.children) != 3:
                raise ValueError("subsup math nodes require three children.")
        elif self.kind == "sqrt":
            if len(self.children) != 1:
                raise ValueError("sqrt math nodes require one child.")


def identifier(value: str) -> MathExpr:
    return MathExpr("identifier", text=str(value))


def number(value: str | float) -> MathExpr:
    return MathExpr("number", text=str(value))


def operator(value: str) -> MathExpr:
    return MathExpr("operator", text=str(value))


def text(value: str) -> MathExpr:
    return MathExpr("text", text=str(value))


def row(*items: MathExpr) -> MathExpr:
    flattened: list[MathExpr] = []
    for item in items:
        if item.kind == "row":
            flattened.extend(item.children)
        else:
            flattened.append(item)
    return MathExpr("row", children=tuple(flattened))


def fraction(numerator: MathExpr, denominator: MathExpr) -> MathExpr:
    return MathExpr("fraction", children=(numerator, denominator))


def sqrt(value: MathExpr) -> MathExpr:
    return MathExpr("sqrt", children=(value,))


def sub(base: MathExpr, script: MathExpr | str) -> MathExpr:
    script_expr = identifier(script) if isinstance(script, str) else script
    return MathExpr("sub", children=(base, script_expr))


def sup(base: MathExpr, script: MathExpr | str | float) -> MathExpr:
    script_expr = number(script) if not isinstance(script, MathExpr) else script
    return MathExpr("sup", children=(base, script_expr))


def subsup(
    base: MathExpr,
    subscript: MathExpr | str,
    superscript: MathExpr | str | float,
) -> MathExpr:
    sub_expr = identifier(subscript) if isinstance(subscript, str) else subscript
    sup_expr = number(superscript) if not isinstance(superscript, MathExpr) else superscript
    return MathExpr("subsup", children=(base, sub_expr, sup_expr))


def parenthesized(value: MathExpr) -> MathExpr:
    return row(operator("("), value, operator(")"))


def absolute(value: MathExpr) -> MathExpr:
    return row(operator("|"), value, operator("|"))


def mathml(expr: MathExpr, *, display: bool = True) -> str:
    """Render the structured expression as browser-native MathML."""

    def render(node: MathExpr) -> str:
        if node.kind == "identifier":
            return f"<mi>{escape(node.text)}</mi>"
        if node.kind == "number":
            return f"<mn>{escape(node.text)}</mn>"
        if node.kind == "operator":
            return f"<mo>{escape(node.text)}</mo>"
        if node.kind == "text":
            return f"<mtext>{escape(node.text)}</mtext>"
        if node.kind == "row":
            return "<mrow>" + "".join(render(child) for child in node.children) + "</mrow>"
        if node.kind == "fraction":
            return f"<mfrac>{render(node.children[0])}{render(node.children[1])}</mfrac>"
        if node.kind == "sqrt":
            return f"<msqrt>{render(node.children[0])}</msqrt>"
        if node.kind == "sub":
            return f"<msub>{render(node.children[0])}{render(node.children[1])}</msub>"
        if node.kind == "sup":
            return f"<msup>{render(node.children[0])}{render(node.children[1])}</msup>"
        if node.kind == "subsup":
            return (
                f"<msubsup>{render(node.children[0])}"
                f"{render(node.children[1])}{render(node.children[2])}</msubsup>"
            )
        raise ValueError(f"Unsupported math node kind: {node.kind}")

    display_attr = "block" if display else "inline"
    return (
        f'<math class="engineering-math" display="{display_attr}" '
        'xmlns="http://www.w3.org/1998/Math/MathML">'
        + render(expr)
        + "</math>"
    )


def plain_math(expr: MathExpr) -> str:
    """Readable text fallback for GUI/accessibility and tests."""

    if expr.kind in {"identifier", "number", "operator", "text"}:
        return expr.text
    if expr.kind == "row":
        return " ".join(plain_math(child) for child in expr.children)
    if expr.kind == "fraction":
        return f"({plain_math(expr.children[0])})/({plain_math(expr.children[1])})"
    if expr.kind == "sqrt":
        return f"sqrt({plain_math(expr.children[0])})"
    if expr.kind == "sub":
        return f"{plain_math(expr.children[0])}_{plain_math(expr.children[1])}"
    if expr.kind == "sup":
        return f"{plain_math(expr.children[0])}^{plain_math(expr.children[1])}"
    if expr.kind == "subsup":
        return (
            f"{plain_math(expr.children[0])}_{plain_math(expr.children[1])}"
            f"^{plain_math(expr.children[2])}"
        )
    raise ValueError(f"Unsupported math node kind: {expr.kind}")


@dataclass(frozen=True)
class _Metrics:
    width: float
    ascent: float
    descent: float


def _font_for(node: MathExpr) -> str:
    return "Times-Italic" if node.kind == "identifier" else "Times-Roman"


def _operator_padding(text_value: str, font_size: float) -> float:
    if text_value in {"=", "+", "−", "-", "×", "·", "≤", "≥", "<", ">", "±"}:
        return 0.14 * font_size
    return 0.04 * font_size


def _measure(node: MathExpr, font_size: float) -> _Metrics:
    if node.kind in {"identifier", "number", "operator", "text"}:
        padding = _operator_padding(node.text, font_size) if node.kind == "operator" else 0.0
        width = pdfmetrics.stringWidth(node.text, _font_for(node), font_size) + 2.0 * padding
        return _Metrics(width=width, ascent=0.78 * font_size, descent=0.22 * font_size)

    if node.kind == "row":
        metrics = [_measure(child, font_size) for child in node.children]
        return _Metrics(
            width=sum(item.width for item in metrics),
            ascent=max(item.ascent for item in metrics),
            descent=max(item.descent for item in metrics),
        )

    if node.kind == "fraction":
        child_size = 0.82 * font_size
        numerator = _measure(node.children[0], child_size)
        denominator = _measure(node.children[1], child_size)
        padding = 0.28 * font_size
        gap = 0.14 * font_size
        line = 0.05 * font_size
        ascent = gap + line + numerator.descent + numerator.ascent
        descent = gap + denominator.ascent + denominator.descent
        return _Metrics(
            width=max(numerator.width, denominator.width) + 2.0 * padding,
            ascent=ascent,
            descent=descent,
        )

    if node.kind == "sqrt":
        inner = _measure(node.children[0], font_size)
        return _Metrics(
            width=inner.width + 0.72 * font_size,
            ascent=inner.ascent + 0.16 * font_size,
            descent=max(inner.descent, 0.28 * font_size),
        )

    if node.kind in {"sub", "sup", "subsup"}:
        base = _measure(node.children[0], font_size)
        script_size = 0.68 * font_size
        subscript = _measure(node.children[1], script_size)
        if node.kind == "sub":
            return _Metrics(
                width=base.width + subscript.width,
                ascent=base.ascent,
                descent=max(base.descent, 0.42 * font_size + subscript.descent),
            )
        if node.kind == "sup":
            return _Metrics(
                width=base.width + subscript.width,
                ascent=max(base.ascent, 0.52 * font_size + subscript.ascent),
                descent=base.descent,
            )
        superscript = _measure(node.children[2], script_size)
        return _Metrics(
            width=base.width + max(subscript.width, superscript.width),
            ascent=max(base.ascent, 0.52 * font_size + superscript.ascent),
            descent=max(base.descent, 0.42 * font_size + subscript.descent),
        )

    raise ValueError(f"Unsupported math node kind: {node.kind}")


def _draw(node: MathExpr, canvas, x: float, baseline: float, font_size: float) -> float:
    if node.kind in {"identifier", "number", "operator", "text"}:
        padding = _operator_padding(node.text, font_size) if node.kind == "operator" else 0.0
        canvas.setFont(_font_for(node), font_size)
        canvas.drawString(x + padding, baseline, node.text)
        return _measure(node, font_size).width

    if node.kind == "row":
        cursor = x
        for child in node.children:
            cursor += _draw(child, canvas, cursor, baseline, font_size)
        return cursor - x

    if node.kind == "fraction":
        child_size = 0.82 * font_size
        numerator = _measure(node.children[0], child_size)
        denominator = _measure(node.children[1], child_size)
        metrics = _measure(node, font_size)
        gap = 0.14 * font_size
        line_y = baseline + 0.04 * font_size
        numerator_baseline = line_y + gap + numerator.descent
        denominator_baseline = line_y - gap - denominator.ascent
        _draw(
            node.children[0],
            canvas,
            x + (metrics.width - numerator.width) / 2.0,
            numerator_baseline,
            child_size,
        )
        _draw(
            node.children[1],
            canvas,
            x + (metrics.width - denominator.width) / 2.0,
            denominator_baseline,
            child_size,
        )
        canvas.setLineWidth(max(0.45, 0.045 * font_size))
        canvas.line(
            x + 0.12 * font_size,
            line_y,
            x + metrics.width - 0.12 * font_size,
            line_y,
        )
        return metrics.width

    if node.kind == "sqrt":
        inner = _measure(node.children[0], font_size)
        metrics = _measure(node, font_size)
        radical_x = x + 0.05 * font_size
        top_y = baseline + inner.ascent + 0.10 * font_size
        canvas.setLineWidth(max(0.45, 0.045 * font_size))
        canvas.line(radical_x, baseline - 0.08 * font_size, radical_x + 0.14 * font_size, baseline - 0.28 * font_size)
        canvas.line(radical_x + 0.14 * font_size, baseline - 0.28 * font_size, radical_x + 0.34 * font_size, top_y)
        canvas.line(radical_x + 0.34 * font_size, top_y, x + metrics.width, top_y)
        _draw(
            node.children[0],
            canvas,
            x + 0.50 * font_size,
            baseline,
            font_size,
        )
        return metrics.width

    if node.kind in {"sub", "sup", "subsup"}:
        base = node.children[0]
        base_metrics = _measure(base, font_size)
        _draw(base, canvas, x, baseline, font_size)
        script_size = 0.68 * font_size
        script_x = x + base_metrics.width
        if node.kind in {"sub", "subsup"}:
            _draw(
                node.children[1],
                canvas,
                script_x,
                baseline - 0.38 * font_size,
                script_size,
            )
        if node.kind == "sup":
            _draw(
                node.children[1],
                canvas,
                script_x,
                baseline + 0.48 * font_size,
                script_size,
            )
        elif node.kind == "subsup":
            _draw(
                node.children[2],
                canvas,
                script_x,
                baseline + 0.48 * font_size,
                script_size,
            )
        return _measure(node, font_size).width

    raise ValueError(f"Unsupported math node kind: {node.kind}")


class MathFormulaFlowable(Flowable):
    """ReportLab flowable that draws real stacked fractions/radicals/subscripts."""

    def __init__(
        self,
        expression: MathExpr,
        *,
        font_size: float = 9.5,
        min_font_size: float = 6.5,
        leading_padding: float = 2.0,
    ) -> None:
        super().__init__()
        self.expression = expression
        self.font_size = float(font_size)
        self.min_font_size = float(min_font_size)
        self.leading_padding = float(leading_padding)
        self._scale = 1.0
        self._metrics = _measure(expression, self.font_size)

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        del availHeight
        natural = self._metrics
        if natural.width <= availWidth:
            self._scale = 1.0
        else:
            # Always fit the available cell width. Very long substitutions are
            # permitted to fall below the preferred minimum font size rather
            # than overflowing into the result column.
            self._scale = max(availWidth / natural.width, 0.05)
        width = min(availWidth, natural.width * self._scale)
        height = (natural.ascent + natural.descent) * self._scale + 2.0 * self.leading_padding
        self.width = width
        self.height = height
        return width, height

    def draw(self) -> None:
        self.canv.saveState()
        self.canv.scale(self._scale, self._scale)
        baseline = self.leading_padding / self._scale + self._metrics.descent
        _draw(
            self.expression,
            self.canv,
            0.0,
            baseline,
            self.font_size,
        )
        self.canv.restoreState()
