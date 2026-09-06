from mcp_reality_check.generator import generate_realistic_arguments, string_argument_values


def test_generates_realistic_value_for_known_property_names():
    schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}, "email": {"type": "string"}},
        "required": ["city", "email"],
    }
    args = generate_realistic_arguments(schema)
    assert args["city"] == "Paris"
    assert "@" in args["email"]


def test_generic_property_name_falls_back_to_a_readable_string():
    schema = {
        "type": "object",
        "properties": {"widget_label": {"type": "string"}},
        "required": ["widget_label"],
    }
    args = generate_realistic_arguments(schema)
    assert "widget label" in args["widget_label"]


def test_hint_matching_is_whole_word_not_substring():
    # "id" is a substring of "widget" (w-i-d-...) — a naive `in` check on
    # the raw property name would wrongly match the "id" hint here. Caught
    # this while writing the test above; fixed via whole-token matching.
    schema = {
        "type": "object",
        "properties": {
            "widget_label": {"type": "string"},
            "video_title": {"type": "string"},
            "provider": {"type": "string"},
        },
        "required": ["widget_label", "video_title", "provider"],
    }
    args = generate_realistic_arguments(schema)
    assert args["widget_label"] != "example-id-123"
    assert args["video_title"] != "example-id-123"
    assert args["provider"] != "example-id-123"


def test_id_hint_still_matches_a_real_id_property():
    schema = {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}
    args = generate_realistic_arguments(schema)
    assert args["user_id"] == "example-id-123"


def test_respects_enum_and_const():
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["fast", "slow"]},
            "version": {"const": 2},
        },
        "required": ["mode", "version"],
    }
    args = generate_realistic_arguments(schema)
    assert args["mode"] == "fast"
    assert args["version"] == 2


def test_only_required_properties_are_included():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["a"],
    }
    args = generate_realistic_arguments(schema)
    assert "a" in args
    assert "b" not in args


def test_handles_array_and_nested_object():
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}},
            "address": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
        "required": ["tags", "address"],
    }
    args = generate_realistic_arguments(schema)
    assert isinstance(args["tags"], list) and len(args["tags"]) == 1
    assert args["address"]["city"] == "Paris"


def test_no_schema_returns_empty_arguments():
    assert generate_realistic_arguments(None) == {}
    assert generate_realistic_arguments({}) == {}


def test_string_argument_values_flattens_and_filters_short_values():
    args = {"city": "Paris", "count": 3, "tags": ["ok", "example thing"], "nested": {"x": "Berlin"}}
    values = string_argument_values(args)
    assert "Paris" in values
    assert "Berlin" in values
    assert "ok" not in values  # too short to be a meaningful signal
    assert "example thing" not in values  # generic fallback, filtered out
