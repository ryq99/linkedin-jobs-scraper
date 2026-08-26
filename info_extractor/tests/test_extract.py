"""Offline tests for the extraction loop — the Ollama client is faked, so no
daemon or model is needed."""

from types import SimpleNamespace

import extract
from schema import JobSkills, RoleFamily


class _FakeClient:
    """Stands in for ollama.Client; returns a canned content string per call."""

    def __init__(self, content: str):
        self._content = content

    def chat(self, **kwargs):  # signature-compatible with ollama.Client.chat
        return SimpleNamespace(message=SimpleNamespace(content=self._content))


_VALID = '{"canonical_title": "ML Engineer", "role_family": "MLE", "seniority": "senior", ' \
         '"years_experience_min": 5, "modeling_area": ["NLP"], "must_have_skills": ["Python"], ' \
         '"nice_to_have_skills": [], "tools": ["PyTorch"], "education_req": "Masters", "domain": ["ads"]}'


def test_model_schema_excludes_owned_fields():
    props = extract._FORMAT["properties"]
    for owned in ("job_id", "extract_model", "extract_dt", "schema_version"):
        assert owned not in props
    assert "role_family" in props  # model-filled fields remain


def test_extract_one_validates_and_stamps_provenance():
    js = extract.extract_one(_FakeClient(_VALID), "qwen2.5:14b", "job-123", "some description")
    assert isinstance(js, JobSkills)
    assert js.job_id == "job-123"                 # authoritative, not from the model
    assert js.role_family is RoleFamily.MLE
    assert js.extract_model == "qwen2.5:14b"
    assert js.extract_dt                          # stamped


def test_extract_one_returns_none_on_bad_output():
    assert extract.extract_one(_FakeClient("not json"), "m", "job-1", "d") is None
    bad_enum = '{"role_family": "Wizard"}'
    assert extract.extract_one(_FakeClient(bad_enum), "m", "job-2", "d") is None
