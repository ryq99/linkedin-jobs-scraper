"""Offline tests for the info_extractor contract, config, and prompt (no LLM)."""

import pytest
from pydantic import ValidationError

import config
import prompt
from schema import Education, JobSkills, ModelingArea, RoleFamily, Seniority


def test_jobskills_accepts_valid_record():
    js = JobSkills(job_id="1", role_family="MLE", modeling_area=["NLP", "RAG"], must_have_skills=["Python"])
    assert js.role_family is RoleFamily.MLE
    dumped = js.model_dump(mode="json")
    assert dumped["role_family"] == "MLE"          # enum -> plain string for SQLite
    assert dumped["modeling_area"] == ["NLP", "RAG"]


@pytest.mark.parametrize("bad", [{"role_family": "Wizard"}, {"years_experience_min": "lots"}, {"nope": 1}])
def test_jobskills_rejects_bad_enum_type_and_extra(bad):
    with pytest.raises(ValidationError):
        JobSkills(job_id="1", **bad)


def test_system_prompt_lists_every_enum_value():
    for enum_cls in (RoleFamily, Seniority, ModelingArea, Education):
        for member in enum_cls:
            assert member.value in prompt.SYSTEM


def test_build_messages_appends_target_after_fewshot():
    msgs = prompt.build_messages("Senior MLE, must have Python")
    # a few-shot user/assistant pair precedes the real posting (the last turn)
    assert len(msgs) >= 3
    assert msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
    assert msgs[-1]["role"] == "user"
    assert "Senior MLE, must have Python" in msgs[-1]["content"]


def test_config_is_populated_from_env():
    assert config.OLLAMA_MODEL            # loaded from .env.example via conftest
    assert config.OLLAMA_HOST.startswith("http")
    assert config.COMMIT_CHUNK > 0
    assert str(config.DB_PATH).endswith("data/jobs.db")
