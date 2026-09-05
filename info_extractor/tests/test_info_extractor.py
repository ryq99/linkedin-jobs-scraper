"""Offline tests for the info_extractor contract, config, and prompt (no LLM)."""

import pytest
from pydantic import ValidationError

import config
import prompt
from schema import Education, JobSkills, Seniority


def test_jobskills_accepts_valid_record():
    js = JobSkills(
        job_id="1",
        tech_domain=["NLP", "RAG"],
        skills=["distributed training"],
        programming_languages=["Python"],
        seniority="senior",
        education_level="Masters",
    )
    assert js.seniority is Seniority.SENIOR
    dumped = js.model_dump(mode="json")
    assert dumped["seniority"] == "senior"           # enum -> plain string for SQLite
    assert dumped["tech_domain"] == ["NLP", "RAG"]
    assert dumped["education_level"] == "Masters"


@pytest.mark.parametrize("bad", [{"seniority": "Wizard"}, {"years_experience_min": "lots"}, {"nope": 1}])
def test_jobskills_rejects_bad_enum_type_and_extra(bad):
    with pytest.raises(ValidationError):
        JobSkills(job_id="1", **bad)


def test_system_prompt_lists_stable_enum_values():
    # Only the two stable fields are enum-constrained in the prompt.
    for enum_cls in (Seniority, Education):
        for member in enum_cls:
            assert member.value in prompt.SYSTEM


def test_system_prompt_names_open_dims():
    for field in ("industry", "business_domain", "tech_domain", "skills",
                  "programming_languages", "team_or_product_area"):
        assert field in prompt.SYSTEM


def test_build_messages_appends_target_after_fewshot():
    msgs = prompt.build_messages("Senior MLE, must have Python")
    assert len(msgs) >= 3
    assert msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
    assert msgs[-1]["role"] == "user"
    assert "Senior MLE, must have Python" in msgs[-1]["content"]


def test_config_is_populated_from_env():
    assert config.OLLAMA_MODEL            # loaded from .env.example via conftest
    assert config.OLLAMA_HOST.startswith("http")
    assert config.COMMIT_CHUNK > 0
    assert str(config.DB_PATH).endswith("data/jobs.db")
