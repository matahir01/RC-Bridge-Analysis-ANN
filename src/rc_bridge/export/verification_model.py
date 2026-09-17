from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerificationNode:
    node_id: int
    x_m: float
    y_m: float
    z_m: float

    def __post_init__(self) -> None:
        if self.node_id <= 0:
            raise ValueError("node_id must be positive.")


@dataclass(frozen=True)
class VerificationMaterial:
    material_id: int
    name: str
    elastic_modulus_kn_m2: float
    poisson_ratio: float = 0.2
    weight_density_kn_m3: float = 25.0
    thermal_expansion_per_c: float = 1.0e-5

    def __post_init__(self) -> None:
        if self.material_id <= 0:
            raise ValueError("material_id must be positive.")
        if not self.name.strip():
            raise ValueError("Material name cannot be empty.")
        if self.elastic_modulus_kn_m2 <= 0.0:
            raise ValueError("Elastic modulus must be positive.")
        if not -1.0 < self.poisson_ratio < 0.5:
            raise ValueError("Poisson ratio must be between -1 and 0.5.")
        if self.weight_density_kn_m3 <= 0.0:
            raise ValueError("Weight density must be positive.")


@dataclass(frozen=True)
class VerificationSection:
    section_id: int
    name: str
    area_m2: float
    torsion_constant_m4: float
    iy_m4: float
    iz_m4: float
    shear_area_y_m2: float | None = None
    shear_area_z_m2: float | None = None

    def __post_init__(self) -> None:
        if self.section_id <= 0:
            raise ValueError("section_id must be positive.")
        if not self.name.strip():
            raise ValueError("Section name cannot be empty.")
        if min(self.area_m2, self.torsion_constant_m4, self.iy_m4, self.iz_m4) <= 0.0:
            raise ValueError("Section area and inertias must be positive.")
        for value in (self.shear_area_y_m2, self.shear_area_z_m2):
            if value is not None and value <= 0.0:
                raise ValueError("Optional shear areas must be positive when supplied.")


@dataclass(frozen=True)
class VerificationBeam:
    member_id: int
    node_i: int
    node_j: int
    material_id: int
    section_id: int
    beta_angle_deg: float = 0.0

    def __post_init__(self) -> None:
        if min(self.member_id, self.node_i, self.node_j, self.material_id, self.section_id) <= 0:
            raise ValueError("Member and reference IDs must be positive.")
        if self.node_i == self.node_j:
            raise ValueError("Beam end nodes must be different.")


@dataclass(frozen=True)
class VerificationSupport:
    node_id: int
    ux: bool = False
    uy: bool = False
    uz: bool = True
    rx: bool = False
    ry: bool = False
    rz: bool = False

    def __post_init__(self) -> None:
        if self.node_id <= 0:
            raise ValueError("Support node_id must be positive.")
        if not any((self.ux, self.uy, self.uz, self.rx, self.ry, self.rz)):
            raise ValueError("A support must restrain at least one degree of freedom.")

    @property
    def restraint_code(self) -> str:
        return "".join("1" if value else "0" for value in (self.ux, self.uy, self.uz, self.rx, self.ry, self.rz))


@dataclass(frozen=True)
class VerificationUniformLoad:
    member_id: int
    direction: str
    magnitude_kn_m: float
    start_m: float | None = None
    end_m: float | None = None

    def __post_init__(self) -> None:
        if self.member_id <= 0:
            raise ValueError("Uniform-load member_id must be positive.")
        if self.direction not in {"GX", "GY", "GZ", "LX", "LY", "LZ"}:
            raise ValueError("Unsupported uniform-load direction.")
        if (self.start_m is None) != (self.end_m is None):
            raise ValueError("Partial UDL requires both start_m and end_m.")
        if self.start_m is not None:
            if self.start_m < 0.0 or self.end_m is None or self.end_m <= self.start_m:
                raise ValueError("Partial UDL distances are invalid.")


@dataclass(frozen=True)
class VerificationPointLoad:
    member_id: int
    direction: str
    magnitude_kn: float
    distance_from_i_m: float

    def __post_init__(self) -> None:
        if self.member_id <= 0:
            raise ValueError("Point-load member_id must be positive.")
        if self.direction not in {"GX", "GY", "GZ", "LX", "LY", "LZ"}:
            raise ValueError("Unsupported point-load direction.")
        if self.distance_from_i_m < 0.0:
            raise ValueError("Point-load distance cannot be negative.")


@dataclass(frozen=True)
class VerificationNodalLoad:
    node_id: int
    fx_kn: float = 0.0
    fy_kn: float = 0.0
    fz_kn: float = 0.0
    mx_knm: float = 0.0
    my_knm: float = 0.0
    mz_knm: float = 0.0

    def __post_init__(self) -> None:
        if self.node_id <= 0:
            raise ValueError("Nodal-load node_id must be positive.")


@dataclass(frozen=True)
class VerificationLoadCase:
    load_case_id: int
    name: str
    self_weight_gz_factor: float = 0.0
    uniform_loads: tuple[VerificationUniformLoad, ...] = ()
    point_loads: tuple[VerificationPointLoad, ...] = ()
    nodal_loads: tuple[VerificationNodalLoad, ...] = ()

    def __post_init__(self) -> None:
        if self.load_case_id <= 0:
            raise ValueError("load_case_id must be positive.")
        if not self.name.strip():
            raise ValueError("Load-case name cannot be empty.")


@dataclass(frozen=True)
class VerificationModel:
    name: str
    nodes: tuple[VerificationNode, ...]
    materials: tuple[VerificationMaterial, ...]
    sections: tuple[VerificationSection, ...]
    beams: tuple[VerificationBeam, ...]
    supports: tuple[VerificationSupport, ...]
    load_cases: tuple[VerificationLoadCase, ...]
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Verification model name cannot be empty.")
        if not self.nodes or not self.materials or not self.sections or not self.beams:
            raise ValueError("Verification model requires nodes, materials, sections and beams.")
        self._require_unique("node", [item.node_id for item in self.nodes])
        self._require_unique("material", [item.material_id for item in self.materials])
        self._require_unique("section", [item.section_id for item in self.sections])
        self._require_unique("member", [item.member_id for item in self.beams])
        self._require_unique("load case", [item.load_case_id for item in self.load_cases])

        node_ids = {item.node_id for item in self.nodes}
        material_ids = {item.material_id for item in self.materials}
        section_ids = {item.section_id for item in self.sections}
        member_ids = {item.member_id for item in self.beams}
        for beam in self.beams:
            if beam.node_i not in node_ids or beam.node_j not in node_ids:
                raise ValueError("Beam references an unknown node.")
            if beam.material_id not in material_ids:
                raise ValueError("Beam references an unknown material.")
            if beam.section_id not in section_ids:
                raise ValueError("Beam references an unknown section.")
        for support in self.supports:
            if support.node_id not in node_ids:
                raise ValueError("Support references an unknown node.")
        for case in self.load_cases:
            for load in (*case.uniform_loads, *case.point_loads):
                if load.member_id not in member_ids:
                    raise ValueError("Member load references an unknown beam.")
            for load in case.nodal_loads:
                if load.node_id not in node_ids:
                    raise ValueError("Nodal load references an unknown node.")

    @staticmethod
    def _require_unique(label: str, values: list[int]) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {label} IDs are not allowed.")

    def member_length_m(self, member_id: int) -> float:
        beam = next((item for item in self.beams if item.member_id == member_id), None)
        if beam is None:
            raise KeyError(f"Unknown member {member_id}.")
        nodes = {item.node_id: item for item in self.nodes}
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        dx = nj.x_m - ni.x_m
        dy = nj.y_m - ni.y_m
        dz = nj.z_m - ni.z_m
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    def validate_load_positions(self) -> None:
        for case in self.load_cases:
            for load in case.uniform_loads:
                if load.end_m is not None and load.end_m > self.member_length_m(load.member_id) + 1e-9:
                    raise ValueError("Partial UDL extends beyond its member length.")
            for load in case.point_loads:
                if load.distance_from_i_m > self.member_length_m(load.member_id) + 1e-9:
                    raise ValueError("Point load lies beyond its member length.")
