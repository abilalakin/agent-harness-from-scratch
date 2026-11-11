from datetime import datetime

from harness.tools import BUILTIN_TOOLS, Tool, cap_output, run_tool_call

TOOLS = {t.name: t for t in BUILTIN_TOOLS}


def call(name, args):
    return {"id": "c1", "type": "function", "function": {"name": name, "arguments": args}}


def test_calculate_with_json_string_args():
    assert run_tool_call(TOOLS, call("calculate", '{"a": 6, "op": "*", "b": 7}')) == "42.0"


def test_calculate_accepts_dict_args_and_number_strings():
    assert run_tool_call(TOOLS, call("calculate", {"a": "6", "op": "*", "b": "7"})) == "42.0"


def test_divide_by_zero_is_tool_error():
    out = run_tool_call(TOOLS, call("calculate", '{"a": 1, "op": "/", "b": 0}'))
    assert out.startswith("Error: tool 'calculate' failed:")


def test_unknown_op_is_tool_error():
    out = run_tool_call(TOOLS, call("calculate", '{"a": 1, "op": "^", "b": 2}'))
    assert out.startswith("Error: tool 'calculate' failed:")


def test_unknown_tool_lists_available():
    out = run_tool_call(TOOLS, call("weather", "{}"))
    assert out == "Error: unknown tool 'weather'. Available tools: get_current_time, calculate"


def test_bad_json():
    out = run_tool_call(TOOLS, call("calculate", "{a: 1"))
    assert out.startswith("Error: arguments are not valid JSON:")


def test_missing_argument():
    out = run_tool_call(TOOLS, call("calculate", '{"a": 1}'))
    assert out.startswith("Error: bad arguments for 'calculate':")


def test_empty_arguments_mean_no_arguments():
    datetime.fromisoformat(run_tool_call(TOOLS, call("get_current_time", "")))


def test_time_bad_timezone_is_tool_error():
    out = run_tool_call(TOOLS, call("get_current_time", '{"timezone": "Mars/Base"}'))
    assert out.startswith("Error: tool 'get_current_time' failed:")


def test_time_valid_timezone_returns_iso():
    datetime.fromisoformat(run_tool_call(TOOLS, call("get_current_time", '{"timezone": "Europe/Istanbul"}')))


def test_schema_shape():
    s = TOOLS["calculate"].schema()
    assert s["type"] == "function" and s["function"]["name"] == "calculate"
    assert s["function"]["parameters"]["required"] == ["a", "op", "b"]


def test_cap_output_short_text_unchanged():
    assert cap_output("abc", limit=10) == "abc"


def test_cap_output_says_so_first():
    out = cap_output("x" * 25, limit=10)
    assert out.startswith("[cut: showing the first 10 of 25 characters.")
    assert out.endswith("\n" + "x" * 10)


def test_run_tool_call_caps_long_results():
    big = Tool("big", "", {"type": "object", "properties": {}}, lambda: "y" * 5000)
    out = run_tool_call({"big": big}, call("big", "{}"))
    assert out.startswith("[cut: showing the first 3000 of 5000 characters.")
