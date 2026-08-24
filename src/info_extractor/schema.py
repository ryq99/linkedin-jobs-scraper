"""Typed record extracted from a job_description by the info_extractor.

One JobSkills per posting, keyed by job_id back to the scraped `jobs` table.
Missing values are None / empty list (never sentinel strings), matching the
convention in src/schemas.py. The constrained fields draw from the enums below,
which double as the allowed-value sets for the extraction prompt/schema.
"""

from dataclasses import dataclass, field, fields
from enum import Enum

SCHEMA_VERSION = 1  # bump when fields/enums change, to target re-extraction


class RoleFamily(str, Enum):
    DS = "DS"                # data scientist / analytics-leaning
    MLE = "MLE"              # ML / software engineer shipping models to prod
    RESEARCH = "Research"    # research scientist / applied research
    MLOPS = "MLOps"          # platform / infra / model deployment
    GENAI = "GenAI"          # LLM / RAG / agent application engineering
    OTHER = "Other"


class Seniority(str, Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    MANAGER = "manager"


class ModelingArea(str, Enum):
    DS = "DS"
    ML = "ML"
    NLP = "NLP"
    CV = "CV"
    RECSYS = "RecSys"
    RAG = "RAG"
    AGENT = "Agent"
    GENAI = "GenAI"


class Education(str, Enum):
    NONE = "none"
    BACHELORS = "Bachelors"
    MASTERS = "Masters"
    PHD = "PhD"


@dataclass
class JobSkills:
    """The extraction target the LLM fills for one posting."""

    job_id: str  # FK to jobs.job_id

    # normalization + classification
    canonical_title: str | None = None
    role_family: str | None = None            # a RoleFamily value
    seniority: str | None = None              # a Seniority value
    years_experience_min: int | None = None
    modeling_area: list[str] = field(default_factory=list)   # ModelingArea values

    # extraction
    must_have_skills: list[str] = field(default_factory=list)
    nice_to_have_skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    education_req: str | None = None          # an Education value
    domain: list[str] = field(default_factory=list)

    # provenance
    extract_model: str | None = None
    extract_dt: str | None = None
    schema_version: int = SCHEMA_VERSION


JOBSKILLS_FIELDS = [f.name for f in fields(JobSkills)]
