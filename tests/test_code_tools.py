
import pytest
from harness.code_tools import OUT_DIR, make_code_tools, run_python
from harness.tools import run_tool_call


def test_stdout_comes_back(tmp_path):
    assert run_python(tmp_path, "print(2 + 2)", sandbox="none") == "4\n"


def test_cwd_is_the_data_folder_and_files_are_readable(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    assert run_python(tmp_path, "print(open('a.txt').read())", sandbox="none") == "hello\n"


def test_stderr_and_exit_code_are_reported(tmp_path):
    out = run_python(tmp_path, "import sys; print('partial'); sys.exit(3)", sandbox="none")
    assert out.startswith("partial\n") and "[exit code 3]" in out


def test_a_crash_shows_the_traceback(tmp_path):
    out = run_python(tmp_path, "1/0", sandbox="none")
    assert "[stderr]" in out and "ZeroDivisionError" in out and "[exit code 1]" in out


def test_files_written_to_out_are_listed(tmp_path):
    code = "from pathlib import Path; Path('out/r.csv').write_text('a,b\\n1,2\\n')"
    out = run_python(tmp_path, code, sandbox="none")
    assert "[wrote out/r.csv (1 KB)]" in out and (tmp_path / OUT_DIR / "r.csv").read_text() == "a,b\n1,2\n"


def test_no_output_says_so(tmp_path):
    assert run_python(tmp_path, "x = 1", sandbox="none") == "(no output)"


def test_endless_script_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.TIMEOUT_SECONDS", 1)
    out = run_python(tmp_path, "print('start', flush=True)\nwhile True: pass", sandbox="none")
    assert out.startswith("Error: the script ran longer than 1 seconds") and "start" in out


def test_huge_output_does_not_block_or_fill_the_context(tmp_path):
    out = run_python(tmp_path, "print('x' * 10_000_000)", sandbox="none")
    assert len(out) < 4000 and out.startswith("[cut:")


def test_memory_limit_stops_a_big_allocation(tmp_path):
    out = run_python(tmp_path, "x = bytearray(2 * 1024**3); print('allocated')", sandbox="none")
    assert "MemoryError" in out and "allocated" not in out


def test_isolated_mode_ignores_a_planted_module(tmp_path):
    (tmp_path / "json.py").write_text("raise SystemExit('planted module imported')")
    assert run_python(tmp_path, "import json; print('ok')", sandbox="none") == "ok\n"


def test_off_means_no_tool(tmp_path):
    assert make_code_tools(tmp_path, "off") == []
    assert [t.name for t in make_code_tools(tmp_path, "none")] == ["run_python"]


# The hole. These pass in "none" mode on purpose: the step note shows them, and the sandbox closes them.
def test_plain_mode_can_read_the_home_folder(tmp_path):
    code = "from pathlib import Path; print(sorted(p.name for p in Path.home().iterdir())[:3])"
    out = run_python(tmp_path, code, sandbox="none")
    assert out.startswith("[") and "Error" not in out


def test_plain_mode_can_write_outside_out(tmp_path):
    run_python(tmp_path, "open('escaped.txt', 'w').write('x')", sandbox="none")
    assert (tmp_path / "escaped.txt").exists()


def test_unknown_sandbox_mode_fails_closed(tmp_path):
    # A typo must never fall through to running the script unsandboxed.
    with pytest.raises(ValueError, match="bwarp"):
        run_python(tmp_path, "print(1)", sandbox="bwarp")


def test_the_model_cannot_pick_the_sandbox_mode(tmp_path):
    # The tool's only argument is `code`. A sandbox argument from the model is a bad argument, not an override.
    (tool,) = make_code_tools(tmp_path, "bwrap")
    call = {"function": {"name": "run_python", "arguments": '{"code": "print(1)", "sandbox": "none"}'}}
    assert run_tool_call({"run_python": tool}, call).startswith("Error: bad arguments")
