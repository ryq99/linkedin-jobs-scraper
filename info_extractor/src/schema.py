"""Typed record extracted from a job_description by the info_extractor.

One JobSkills per posting, keyed by job_id back to the scraped `jobs` table.
JobSkills is a Pydantic model (validates untrusted LLM output; model_json_schema()
feeds the structured-output format from this one source of truth).

Design: the scraper's structured fields (title, salary, location, dates) are the
stable core. This record captures the *details a JD adds on top* — all emergent,
so the detail dimensions are OPEN vocabulary (plain str lists, the model uses the
posting's own terms). Only genuinely stable, low-cardinality fields stay enums
(seniority, education_level) so they compare cleanly across time. Canonical tags
for the open dims are derived later by a separate, versioned taxonomy layer.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = 2  # bump when fields/enums change, to target re-extraction


class Seniority(str, Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    MANAGER = "manager"


class Education(str, Enum):
    NONE = "none"
    BACHELORS = "Bachelors"
    MASTERS = "Masters"
    PHD = "PhD"


class JobSkills(BaseModel):
    """The extraction target the LLM fills for one posting."""

    model_config = ConfigDict(extra="forbid")  # reject fields the model invents

    job_id: str  # FK to jobs.job_id

    # --- open-vocabulary detail dimensions (posting's own terms, no fixed set) ---
    industry: list[str] = []              # tech, fintech, healthcare, entertainment, ...
    business_domain: list[str] = []       # payments, search, risk, marketing, research, ...
    tech_domain: list[str] = []           # forecasting, experimentation, causal, RAG, agents, CV, ...
    skills: list[str] = []                # RAG, CI/CD, monitoring, prototyping, distributed training, ...
    programming_languages: list[str] = []  # Python, Scala, C++, Rust, ...
    team_or_product_area: list[str] = []  # "Search & Personalization", "Payments ML Accelerator", ...
    role_type: list[str] = []             # DS, MLE, Research, MLOps, PM, SWE, ...

    # --- stable normalizations (typed for clean cross-time comparability) ---
    canonical_title: str | None = None
    seniority: Seniority | None = None
    years_experience_min: int | None = None
    education_level: Education | None = None

    # --- provenance ---
    extract_model: str | None = None
    extract_dt: str | None = None
    schema_version: int = SCHEMA_VERSION


JOBSKILLS_FIELDS = list(JobSkills.model_fields)
