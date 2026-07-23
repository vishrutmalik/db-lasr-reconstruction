"""Time types, calendars, id minting, hashing, seeds, provenance enums, typed errors.

Level-0 package (# arch: system_design.md §4): imports nothing from lasr.
G017 slice: the normative time vocabulary (system_design.md §1), the
identity spine (canonical_schemas.md §1), the frozen TimingRecord
(training_and_artifacts.md §4.1, MP §23), and shared enums. Calendars,
hashing, and seed handling land with their consuming goals.
"""

from lasr.core.enums import (
    REGION_SCHEMES,
    ClassificationScheme,
    KnowledgeBasis,
    PitGrade,
    RevisionSupport,
)
from lasr.core.errors import (
    IdentityError,
    LasrError,
    SchemaValidationError,
    TimeSemanticsError,
)
from lasr.core.ids import (
    SECURITY_ID_PREFIX,
    IdScheme,
    IssuerId,
    SecurityId,
    UniverseId,
    mint_security_id,
)
from lasr.core.time_semantics import (
    AsOf,
    DateInterval,
    EventDate,
    EventTime,
    KnowledgeTime,
    VintageSeq,
    ensure_utc,
    knowable,
)
from lasr.core.timing import ExecutionMode, TimingRecord

__all__ = [
    "REGION_SCHEMES",
    "SECURITY_ID_PREFIX",
    "AsOf",
    "ClassificationScheme",
    "DateInterval",
    "EventDate",
    "EventTime",
    "ExecutionMode",
    "IdScheme",
    "IdentityError",
    "IssuerId",
    "KnowledgeBasis",
    "KnowledgeTime",
    "LasrError",
    "PitGrade",
    "RevisionSupport",
    "SchemaValidationError",
    "SecurityId",
    "TimeSemanticsError",
    "TimingRecord",
    "UniverseId",
    "VintageSeq",
    "ensure_utc",
    "knowable",
    "mint_security_id",
]
