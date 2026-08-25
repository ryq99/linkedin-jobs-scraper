"""Prompt assembly for skill/competency extraction.

Pure functions only (no network/DB) so they're trivially unit-testable. Allowed
values for every categorical field come from the schema enums — one vocabulary,
defined once in schema.py — so the prompt can never drift from what JobSkills
will actually validate.
"""

from schema import Education, ModelingArea, RoleFamily, Seniority


def _values(enum_cls) -> str:
    """Comma-joined enum values, for embedding in the instructions."""
    return ", ".join(member.value for member in enum_cls)


SYSTEM = f"""You extract one structured record from a single job posting.

Fill only the schema fields. Follow these rules:
- role_family: exactly one of [{_values(RoleFamily)}].
- seniority: one of [{_values(Seniority)}] — infer from title, required years, and scope.
- modeling_area: zero or more of [{_values(ModelingArea)}].
- education_req: the MINIMUM required degree, one of [{_values(Education)}] ("none" if no degree is required).
- must_have_skills vs nice_to_have_skills: a skill is must-have only if the posting frames it as required
  ("required", "must have", "N+ years of"); "preferred" / "bonus" / "nice to have" / "a plus" go in nice_to_have.
- canonical_title: a short normalized title (e.g. "Machine Learning Engineer"), not the company's decorated title.
- years_experience_min: minimum years required as an integer; 0 for new-grad / intern roles; omit if truly unstated.
- tools: concrete technologies/libraries/platforms (Python, PyTorch, Spark, AWS).
- domain: business domains the role serves (finance, healthcare, ads, ...).

Extract only what the text supports. Never invent a value."""


def build_messages(description: str) -> list[dict]:
    """The request's messages — just the posting to extract (zero-shot).

    The rules live in SYSTEM and the shape is enforced by the JobSkills JSON
    schema, so a single user turn is enough. Prepend a few-shot example here
    later if a validation sample shows judgment errors (must-vs-nice, titles).
    """
    return [{"role": "user", "content": f"Job posting:\n{description}"}]
