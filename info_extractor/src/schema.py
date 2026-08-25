"""Typed record extracted from a job_description by the info_extractor.

One JobSkills per posting, keyed by job_id back to the scraped `jobs` table.
JobSkills is a Pydantic model (not a stdlib dataclass) because it validates
untrusted LLM output: the enum-typed fields reject values Claude invents, and
`model_json_schema()` feeds the API's structured-output format from this one
source of truth. Missing values are None / empty list, matching src/schemas.py.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict

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


class JobSkills(BaseModel):
    """The extraction target the LLM fills for one posting."""

    model_config = ConfigDict(extra="forbid")  # reject fields the model invents

    job_id: str  # FK to jobs.job_id

    # normalization + classification (enum-typed → invalid values are rejected)
    canonical_title: str | None = None
    role_family: RoleFamily | None = None
    seniority: Seniority | None = None
    years_experience_min: int | None = None
    modeling_area: list[ModelingArea] = []

    # extraction
    must_have_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    tools: list[str] = []
    education_req: Education | None = None
    domain: list[str] = []

    # provenance
    extract_model: str | None = None
    extract_dt: str | None = None
    schema_version: int = SCHEMA_VERSION


JOBSKILLS_FIELDS = list(JobSkills.model_fields)
