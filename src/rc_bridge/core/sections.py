from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RectangularSection:
    width_m: float
    depth_m: float

    def __post_init__(self) -> None:
        if self.width_m <= 0 or self.depth_m <= 0:
            raise ValueError("Section dimensions must be positive.")

    @property
    def area_m2(self) -> float:
        return self.width_m * self.depth_m

    @property
    def second_moment_m4(self) -> float:
        return self.width_m * self.depth_m**3 / 12.0


@dataclass(frozen=True)
class TSection:
    flange_width_m: float
    flange_thickness_m: float
    web_width_m: float
    total_depth_m: float

    def __post_init__(self) -> None:
        values = (
            self.flange_width_m,
            self.flange_thickness_m,
            self.web_width_m,
            self.total_depth_m,
        )
        if any(v <= 0 for v in values):
            raise ValueError("Section dimensions must be positive.")
        if self.flange_thickness_m >= self.total_depth_m:
            raise ValueError("Flange thickness must be less than total depth.")
        if self.web_width_m > self.flange_width_m:
            raise ValueError("Web width cannot exceed flange width for a T-section.")

    @property
    def web_depth_m(self) -> float:
        return self.total_depth_m - self.flange_thickness_m

    @property
    def area_m2(self) -> float:
        return (
            self.flange_width_m * self.flange_thickness_m
            + self.web_width_m * self.web_depth_m
        )

    @property
    def centroid_from_top_m(self) -> float:
        af = self.flange_width_m * self.flange_thickness_m
        aw = self.web_width_m * self.web_depth_m
        yf = self.flange_thickness_m / 2.0
        yw = self.flange_thickness_m + self.web_depth_m / 2.0
        return (af * yf + aw * yw) / (af + aw)

    @property
    def second_moment_m4(self) -> float:
        ybar = self.centroid_from_top_m
        af = self.flange_width_m * self.flange_thickness_m
        aw = self.web_width_m * self.web_depth_m
        yf = self.flange_thickness_m / 2.0
        yw = self.flange_thickness_m + self.web_depth_m / 2.0
        iff = self.flange_width_m * self.flange_thickness_m**3 / 12.0
        iww = self.web_width_m * self.web_depth_m**3 / 12.0
        return iff + af * (ybar - yf) ** 2 + iww + aw * (yw - ybar) ** 2


@dataclass(frozen=True)
class ISection:
    top_flange_width_m: float
    top_flange_thickness_m: float
    web_width_m: float
    web_depth_m: float
    bottom_flange_width_m: float
    bottom_flange_thickness_m: float

    def __post_init__(self) -> None:
        values = (
            self.top_flange_width_m,
            self.top_flange_thickness_m,
            self.web_width_m,
            self.web_depth_m,
            self.bottom_flange_width_m,
            self.bottom_flange_thickness_m,
        )
        if any(v <= 0 for v in values):
            raise ValueError("Section dimensions must be positive.")
        if self.web_width_m > max(self.top_flange_width_m, self.bottom_flange_width_m):
            raise ValueError("Web width is inconsistent with flange widths.")

    @property
    def total_depth_m(self) -> float:
        return self.top_flange_thickness_m + self.web_depth_m + self.bottom_flange_thickness_m

    @property
    def area_m2(self) -> float:
        return (
            self.top_flange_width_m * self.top_flange_thickness_m
            + self.web_width_m * self.web_depth_m
            + self.bottom_flange_width_m * self.bottom_flange_thickness_m
        )

    @property
    def centroid_from_top_m(self) -> float:
        a1 = self.top_flange_width_m * self.top_flange_thickness_m
        a2 = self.web_width_m * self.web_depth_m
        a3 = self.bottom_flange_width_m * self.bottom_flange_thickness_m
        y1 = self.top_flange_thickness_m / 2.0
        y2 = self.top_flange_thickness_m + self.web_depth_m / 2.0
        y3 = (
            self.top_flange_thickness_m
            + self.web_depth_m
            + self.bottom_flange_thickness_m / 2.0
        )
        return (a1 * y1 + a2 * y2 + a3 * y3) / (a1 + a2 + a3)

    @property
    def second_moment_m4(self) -> float:
        ybar = self.centroid_from_top_m
        parts = (
            (
                self.top_flange_width_m,
                self.top_flange_thickness_m,
                self.top_flange_thickness_m / 2.0,
            ),
            (
                self.web_width_m,
                self.web_depth_m,
                self.top_flange_thickness_m + self.web_depth_m / 2.0,
            ),
            (
                self.bottom_flange_width_m,
                self.bottom_flange_thickness_m,
                self.top_flange_thickness_m
                + self.web_depth_m
                + self.bottom_flange_thickness_m / 2.0,
            ),
        )
        total = 0.0
        for b, h, y in parts:
            area = b * h
            total += b * h**3 / 12.0 + area * (y - ybar) ** 2
        return total
