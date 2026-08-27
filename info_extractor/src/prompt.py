"""Prompt assembly for skill/competency extraction.

Pure functions only (no network/DB) so they're trivially unit-testable. Allowed
values for every categorical field come from the schema enums — one vocabulary,
defined once in schema.py — so the prompt can never drift from what JobSkills
will actually validate.

Small local models conflate the free-text fields (empty must_have/tools, and a
runaway `domain` dump) unless the routing is spelled out and demonstrated. So the
rules below are explicit about which list each item goes in, and build_messages
prepends one grounded few-shot example.
"""

import json

from schema import Education, ModelingArea, RoleFamily, Seniority


def _values(enum_cls) -> str:
    """Comma-joined enum values, for embedding in the instructions."""
    return ", ".join(member.value for member in enum_cls)


SYSTEM = f"""You extract one structured record from a single job posting. Return only the schema fields.

Field rules:
- canonical_title: ALWAYS output a short, normalized job title (e.g. "Machine Learning Engineer",
  "Data Scientist", "Research Scientist"). Never leave it empty; strip the company's decoration.
- role_family: exactly one of [{_values(RoleFamily)}].
- seniority: one of [{_values(Seniority)}]. Infer from the title and required years
  ("Sr."/"Senior" -> senior, "Staff"/"Principal" accordingly, new-grad/intern -> entry/intern).
  Do not default to "mid" unless the level is genuinely unclear.
- years_experience_min: minimum years of experience required, as an integer (0 for new-grad/intern).
  Infer from phrases like "5+ years". Omit only if there is no signal at all.
- modeling_area: only the few areas that clearly apply, from [{_values(ModelingArea)}]. Never select all.

Put each item in exactly ONE list; never repeat an item across lists:
- must_have_skills: named skills/methods the posting REQUIRES ("required", "must have", "N+ years of X")
  — e.g. "Machine Learning", "Deep Learning", "SQL", "Statistics", "NLP".
- nice_to_have_skills: skills framed as PREFERRED ("preferred", "bonus", "nice to have", "a plus").
- tools: concrete technologies / libraries / platforms / languages (Python, PyTorch, TensorFlow, Spark,
  AWS, Kubernetes), required or preferred alike. Tools go HERE, never in the skill lists or domain.
- education_req: the MINIMUM required degree, one of [{_values(Education)}] ("none" if none required).
- domain: 1-3 BROAD business industries the role serves (finance, healthcare, e-commerce, advertising,
  autonomous driving). Industries ONLY — never skills, tools, tasks, or company values. Empty if unclear.

Extract only what the text supports. Keep every list concise (a handful of the most important items).
Never invent values and never emit long, repetitive lists."""


# One grounded example, demonstrating the field routing the rules describe. Not a
# last-turn prefill (the real posting follows), so it stays valid with structured
# outputs. Its JSON matches the pruned schema the model fills (no job_id/provenance).
_EXAMPLE_USER = """Job posting:
Senior Machine Learning Engineer. You will build recommendation and ranking models for our
e-commerce marketplace. Requires 5+ years of production ML, strong machine learning fundamentals,
and SQL. Must be fluent in Python and PyTorch. Preferred: experience with large language models
and Spark. MS or PhD in Computer Science or a related field."""

_EXAMPLE_ASSISTANT = json.dumps({
    "canonical_title": "Machine Learning Engineer",
    "role_family": "MLE",
    "seniority": "senior",
    "years_experience_min": 5,
    "modeling_area": ["ML", "RecSys"],
    "must_have_skills": ["Machine Learning", "SQL"],
    "nice_to_have_skills": ["Large Language Models"],
    "tools": ["Python", "PyTorch", "Spark"],
    "education_req": "Masters",
    "domain": ["e-commerce"],
})


def build_messages(description: str) -> list[dict]:
    """One grounded few-shot pair, then the posting to extract."""
    return [
        {"role": "user", "content": _EXAMPLE_USER},
        {"role": "assistant", "content": _EXAMPLE_ASSISTANT},
        {"role": "user", "content": f"Job posting:\n{description}"},
    ]
