from mcp_reality_check.checks import (
    check_echo_mismatch,
    check_empty_content,
    check_output_schema,
    check_refusal_in_disguise,
)


def test_refusal_in_disguise_catches_common_phrasings():
    assert check_refusal_in_disguise("I don't have access to real-time data.") is not None
    assert check_refusal_in_disguise("I'm sorry, but I cannot do that.") is not None
    assert check_refusal_in_disguise("As an AI, I have no way to browse the web.") is not None
    assert check_refusal_in_disguise("Unfortunately, I cannot process this request.") is not None


def test_refusal_in_disguise_does_not_flag_a_genuine_answer():
    assert check_refusal_in_disguise("The weather in Paris is sunny and 72F.") is None
    # "sorry" alone, in a non-refusal context, shouldn't trip the check —
    # only specific refusal phrasings should.
    assert check_refusal_in_disguise("Sorry for the delay, here are your results: 3 items found.") is None


def test_empty_content():
    assert check_empty_content("") is True
    assert check_empty_content("   \n  ") is True
    assert check_empty_content("actual content") is False


def test_echo_mismatch_returns_none_when_nothing_to_check():
    assert check_echo_mismatch("some response", []) is None


def test_echo_mismatch_finds_present_and_missing_values():
    response = "The weather in Paris is sunny."
    assert check_echo_mismatch(response, ["Paris"]) == []
    assert check_echo_mismatch(response, ["Paris", "Berlin"]) == ["Berlin"]
    assert check_echo_mismatch(response, ["Berlin"]) == ["Berlin"]


def test_echo_mismatch_is_case_insensitive():
    assert check_echo_mismatch("The weather in PARIS is sunny.", ["Paris"]) == []


def test_output_schema_skips_when_either_side_missing():
    assert check_output_schema(None, {"type": "object"}) is None
    assert check_output_schema({"x": 1}, None) is None


def test_output_schema_catches_a_real_violation():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
    assert check_output_schema({"count": "not a number"}, schema) is not None
    assert check_output_schema({}, schema) is not None


def test_output_schema_passes_a_matching_response():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
    assert check_output_schema({"count": 3}, schema) is None
