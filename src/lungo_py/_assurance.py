"""A program's assurance document (`assurance.json`): what its Lean code claims and proves of each
export, the code each export's proofs do not cover (its trust), and the assumptions about the
host its claims are conditional on. Every generated package carries it as `ASSURANCE`."""

import json
import typing as _t
from dataclasses import dataclass, fields

from ._errors import MalformedError

SCHEMA_VERSION = 1


def _build(cls, data, where):
    if not isinstance(data, dict):
        raise MalformedError(f"{where}: an object is expected")
    names = {f.name for f in fields(cls)}
    extra = set(data) - names
    missing = names - set(data)
    if extra or missing:
        raise MalformedError(f"{where}: unknown fields {sorted(extra)}, missing fields {sorted(missing)}")
    return data


@dataclass(frozen=True)
class Position:
    line: int
    column: int


@dataclass(frozen=True)
class Source:
    package: str
    file: str
    start: _t.Optional[Position]
    end: _t.Optional[Position]


@dataclass(frozen=True)
class Provenance:
    lean_version: str
    lean_githash: str
    lungo_version: str
    bir_version: int
    runtime_abi: int


@dataclass(frozen=True)
class Library:
    package: str
    schema_version: int


@dataclass(frozen=True)
class Specification:
    name: str
    kind: str
    statement: str
    definition: _t.Optional[str]
    package: _t.Optional[str]
    fingerprint: str
    source: _t.Optional[Source]


@dataclass(frozen=True)
class Operation:
    name: str
    symbol: _t.Optional[str]
    fingerprint: _t.Optional[str]


@dataclass(frozen=True)
class Facility:
    name: str
    id: str
    form: str
    op_type: _t.Optional[str]
    operations: _t.Tuple[Operation, ...]
    assumptions: _t.Tuple[str, ...]
    package: _t.Optional[str]
    fingerprint: str
    source: _t.Optional[Source]


@dataclass(frozen=True)
class Assumption:
    name: str
    facility: str
    statement: str
    definition: _t.Optional[str]
    package: _t.Optional[str]
    fingerprint: str
    source: _t.Optional[Source]


@dataclass(frozen=True)
class EvidenceTrust:
    axioms: _t.Tuple[str, ...]
    depends_on_sorry: bool


@dataclass(frozen=True)
class Claim:
    """A theorem (its name is the claim's) proving that its subjects stand in a relation to its
    specifications; `status` is `"proved"` or `"incomplete"` (resting on `sorry`)."""

    name: str
    relation: str
    subjects: _t.Tuple[str, ...]
    specifications: _t.Tuple[str, ...]
    statement: str
    status: str
    evidence_trust: EvidenceTrust
    assumptions: _t.Tuple[str, ...]
    package: _t.Optional[str]
    fingerprint: str
    source: _t.Optional[Source]


@dataclass(frozen=True)
class Role:
    name: str
    role: str
    exported: bool


@dataclass(frozen=True)
class Trust:
    axioms: _t.Tuple[str, ...]
    depends_on_sorry: bool
    unsafe_dependencies: _t.Tuple[str, ...]
    partial_dependencies: _t.Tuple[str, ...]
    extern_dependencies: _t.Tuple[str, ...]


@dataclass(frozen=True)
class Export:
    name: str
    module: str
    async_: bool
    trust: Trust
    claims: _t.Tuple[str, ...]
    assumptions: _t.Tuple[str, ...]
    facilities: _t.Tuple[str, ...]
    roles: _t.Tuple[str, ...]
    source: _t.Optional[Source]


def _opt(cls, v, where):
    return None if v is None else cls._read(v, where)


def _strs(v, where):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise MalformedError(f"{where}: a list of strings is expected")
    return tuple(v)


def _reader(cls, convert):
    def read(data, where):
        d = dict(_build(cls, data, where))
        for k, f in convert.items():
            d[k] = f(d[k], f"{where}.{k}")
        return cls(**d)

    return read


Position._read = staticmethod(_reader(Position, {}))
Source._read = staticmethod(_reader(Source, {"start": lambda v, w: _opt(Position, v, w), "end": lambda v, w: _opt(Position, v, w)}))
Provenance._read = staticmethod(_reader(Provenance, {}))
Library._read = staticmethod(_reader(Library, {}))
_src = {"source": lambda v, w: _opt(Source, v, w)}
Specification._read = staticmethod(_reader(Specification, _src))
Operation._read = staticmethod(_reader(Operation, {}))
Facility._read = staticmethod(
    _reader(
        Facility,
        {
            **_src,
            "operations": lambda v, w: tuple(Operation._read(x, f"{w}[{i}]") for i, x in enumerate(v)),
            "assumptions": _strs,
        },
    )
)
Assumption._read = staticmethod(_reader(Assumption, _src))
EvidenceTrust._read = staticmethod(_reader(EvidenceTrust, {"axioms": _strs}))
Claim._read = staticmethod(
    _reader(
        Claim,
        {
            **_src,
            "subjects": _strs,
            "specifications": _strs,
            "assumptions": _strs,
            "evidence_trust": lambda v, w: EvidenceTrust._read(v, w),
        },
    )
)
Role._read = staticmethod(_reader(Role, {}))
_trust_lists = ("axioms", "unsafe_dependencies", "partial_dependencies", "extern_dependencies")
Trust._read = staticmethod(_reader(Trust, {k: _strs for k in _trust_lists}))


def _read_export(data, where):
    data = dict(data) if isinstance(data, dict) else data
    if isinstance(data, dict) and "async" in data:
        data["async_"] = data.pop("async")
    return _reader(
        Export,
        {
            **_src,
            "trust": lambda v, w: Trust._read(v, w),
            "claims": _strs,
            "assumptions": _strs,
            "facilities": _strs,
            "roles": _strs,
        },
    )(data, where)


@dataclass(frozen=True)
class Assurance:
    schema_version: int
    program: str
    provenance: Provenance
    library: _t.Optional[Library]
    specifications: _t.Tuple[Specification, ...]
    facilities: _t.Tuple[Facility, ...]
    assumptions: _t.Tuple[Assumption, ...]
    claims: _t.Tuple[Claim, ...]
    roles: _t.Tuple[Role, ...]
    exports: _t.Tuple[Export, ...]

    @staticmethod
    def from_json(text: str) -> "Assurance":
        """Reads an assurance document, refusing one of another schema version or with fields this
        library does not know."""
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            raise MalformedError(
                f"assurance schema version {data.get('schema_version') if isinstance(data, dict) else None}; "
                f"this library reads version {SCHEMA_VERSION}"
            )
        _build(Assurance, data, "assurance")

        def many(read, key):
            return tuple(read(x, f"{key}[{i}]") for i, x in enumerate(data[key]))

        return Assurance(
            schema_version=data["schema_version"],
            program=data["program"],
            provenance=Provenance._read(data["provenance"], "provenance"),
            library=_opt(Library, data["library"], "library"),
            specifications=many(Specification._read, "specifications"),
            facilities=many(Facility._read, "facilities"),
            assumptions=many(Assumption._read, "assumptions"),
            claims=many(Claim._read, "claims"),
            roles=many(Role._read, "roles"),
            exports=many(_read_export, "exports"),
        )

    def claim(self, name: str) -> _t.Optional[Claim]:
        """The claim whose evidence is `name`."""
        return next((c for c in self.claims if c.name == name), None)

    def export(self, name: str) -> _t.Optional[Export]:
        """The summary of the export `name`."""
        return next((e for e in self.exports if e.name == name), None)
