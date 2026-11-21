from lavoro import llm, match


def test_strict_schema_requires_every_field_and_no_extras():
    s = llm._strict(match.TriageBatch.model_json_schema())
    item = s["$defs"]["TriageItem"]
    assert item["additionalProperties"] is False and set(item["required"]) == {"id", "keep", "reason"}
    assert s["required"] == ["jobs"] and "title" not in s


def test_strict_keeps_a_property_named_title():
    from pydantic import BaseModel

    class Ad(BaseModel):
        title: str

    s = llm._strict(Ad.model_json_schema())
    assert "title" in s["properties"] and s["required"] == ["title"]
