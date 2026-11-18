
import shutil
from pathlib import Path

import pytest
from harness.code_tools import OUT_DIR, make_code_tools, python_roots, run_python
from harness.practice_data import make_all
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


# --- Inside the sandbox ------------------------------------------------------

needs_bwrap = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not installed")


@needs_bwrap
def test_bwrap_runs_a_script_with_the_same_result(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    assert run_python(tmp_path, "print(open('a.txt').read())") == "hello\n"


@needs_bwrap
def test_bwrap_cannot_see_files_in_the_home_folder(tmp_path):
    # The home folder itself exists inside (the venv lives under it), but none of its files do.
    real_file = next(p for p in Path.home().iterdir() if p.is_file())
    out = run_python(tmp_path, f"import os; print(os.path.exists({str(real_file)!r}), len(os.listdir({str(Path.home())!r})))")
    assert out.startswith("False ")


@needs_bwrap
def test_bwrap_accepts_the_data_prefix_too(tmp_path):
    # Models often write data/legacy/x.xlsx even though the script already runs inside the data folder.
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "a.txt").write_text("hello")
    code = "print(open('legacy/a.txt').read(), open('data/legacy/a.txt').read())"
    assert run_python(tmp_path, code) == "hello hello\n"


@needs_bwrap
def test_bwrap_cannot_write_outside_out(tmp_path):
    out = run_python(tmp_path, "open('escaped.txt', 'w').write('x')")
    assert "Read-only file system" in out and not (tmp_path / "escaped.txt").exists()


@needs_bwrap
def test_bwrap_writes_to_out_arrive_on_the_host(tmp_path):
    out = run_python(tmp_path, "open('out/r.txt', 'w').write('x')")
    assert "[wrote out/r.txt" in out and (tmp_path / "out" / "r.txt").read_text() == "x"


@needs_bwrap
def test_bwrap_has_no_network(tmp_path):
    code = (
        "import socket\n"
        "try: socket.create_connection(('1.1.1.1', 53), timeout=2); print('connected')\n"
        "except OSError as e: print('refused', e.errno)"
    )
    assert run_python(tmp_path, code) == "refused 101\n"


@needs_bwrap
def test_bwrap_endless_script_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.TIMEOUT_SECONDS", 1)
    assert run_python(tmp_path, "while True: pass").startswith("Error: the script ran longer")


@needs_bwrap
def test_bwrap_pandas_reads_the_practice_excel(tmp_path):
    make_all(tmp_path)
    out = run_python(tmp_path, "import pandas; print(len(pandas.read_excel('legacy/customers_export.xlsx')))")
    assert out == "55\n"


def test_missing_bwrap_gives_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.BWRAP", "/nonexistent/bwrap")
    out = run_python(tmp_path, "print(1)")
    assert out.startswith("Error: the sandbox could not start") and "HARNESS_SANDBOX=none" in out


def test_python_roots_follow_the_symlink_chain_and_stay_narrow():
    # Every root is a real Python install (has bin/ and lib/), none is the home folder or above it.
    roots = python_roots()
    assert roots and all((r / "bin").is_dir() and (r / "lib").is_dir() for r in roots)
    assert all(r != Path.home() and r not in Path.home().parents for r in roots)


def test_a_too_broad_python_root_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.python_roots", lambda: [Path.home()])
    out = run_python(tmp_path, "print(1)")
    assert out.startswith("Error: the sandbox could not start: refusing to mount")


def test_a_symlinked_out_folder_is_refused(tmp_path):
    elsewhere = tmp_path.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    (tmp_path / "out").symlink_to(elsewhere)
    out = run_python(tmp_path, "open('out/x.txt', 'w').write('x')", sandbox="none")
    assert out.startswith("Error: data/out is a symlink") and not (elsewhere / "x.txt").exists()
