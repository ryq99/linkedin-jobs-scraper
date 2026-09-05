"""Prompt assembly for JD detail extraction.

Pure functions (no I/O), trivially unit-testable. The detail dimensions are
OPEN vocabulary — the model uses the posting's own concise terms rather than
picking from a fixed list (fixed enums under-tagged and couldn't capture emerging
vocabulary). Only the two stable fields, seniority and education_level, are
constrained to enums; their allowed values come from schema.py so the prompt
can't drift from what JobSkills validates.
"""

import json

from schema import Education, Seniority

_SENIORITY = ", ".join(m.value for m in Seniority)
_EDUCATION = ", ".join(m.value for m in Education)

SYSTEM = f"""You extract structured details from a single job posting for market analysis.

For the OPEN fields below, use the posting's OWN concise terms (short noun phrases,
2-4 words). Do NOT force them into fixed categories, do NOT invent, and leave a list
empty if the posting doesn't support it. Keep each list to the few most salient items.
- industry: the company's sector(s) — e.g. tech, fintech, healthcare, entertainment, retail.
- business_domain: the business function the role serves — e.g. payments, search, risk,
  marketing, fraud, recommendations, research.
- tech_domain: the technical/modeling areas — e.g. forecasting, experimentation, causal
  inference, NLP, computer vision, recommendations, RAG, agents, foundation models, MLOps.
- skills: concrete methods/practices/competencies — e.g. distributed training, prototyping,
  CI/CD, model monitoring, feature engineering, A/B testing, data pipelines.
- programming_languages: languages named — e.g. Python, Scala, Java, C++, Rust, R, SQL.
- team_or_product_area: the specific team/product named — e.g. "Search & Personalization",
  "Payments ML Accelerator", "Prime Video", "Unity Catalog".

For the STABLE fields, choose exactly one value:
- canonical_title: a short normalized title (e.g. "Machine Learning Engineer"); strip
  seniority prefixes, team names, and location. Always output one.
- seniority: one of [{_SENIORITY}]. Infer from title and required years ("Sr."/"Senior" ->
  senior, "Staff"/"Principal" accordingly, new-grad/intern -> entry/intern). Don't default to mid.
- years_experience_min: minimum years required, integer (0 for new-grad/intern); omit if unstated.
- education_level: the MINIMUM required degree, one of [{_EDUCATION}] ("none" if no degree required).

Extract only what the text supports."""


# One grounded few-shot pair — demonstrates OPEN-vocab phrase extraction + the
# field routing. Not a last-turn prefill (the real posting follows), so it stays
# valid with structured outputs.
_EXAMPLE_USER = """Job posting:
Senior Machine Learning Engineer, Payments ML Accelerator at a fintech company. You'll build
deep-learning fraud and authorization-optimization models for our payments platform, run rapid
A/B experiments, and deploy streaming feature pipelines to production. Requires 7+ years of
production ML and fluency in Python, Scala, and Spark. Preferred: LLMs. MS or PhD in a
quantitative field."""

_EXAMPLE_ASSISTANT = json.dumps({
    "industry": ["fintech"],
    "business_domain": ["payments", "fraud"],
    "tech_domain": ["fraud detection", "experimentation", "foundation models"],
    "skills": ["deep learning", "A/B testing", "streaming feature pipelines", "production deployment"],
    "programming_languages": ["Python", "Scala"],
    "team_or_product_area": ["Payments ML Accelerator"],
    "canonical_title": "Machine Learning Engineer",
    "seniority": "senior",
    "years_experience_min": 7,
    "education_level": "Masters",
})


def build_messages(description: str) -> list[dict]:
    """One grounded few-shot pair, then the posting to extract."""
    return [
        {"role": "user", "content": _EXAMPLE_USER},
        {"role": "assistant", "content": _EXAMPLE_ASSISTANT},
        {"role": "user", "content": f"Job posting:\n{description}"},
    ]
