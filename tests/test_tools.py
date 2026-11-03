from datetime import datetime

from harness.tools import BUILTIN_TOOLS, run_tool_call

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
