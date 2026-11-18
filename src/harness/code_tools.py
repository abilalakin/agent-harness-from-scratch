"""A tool that runs a script the model wrote.

The script runs as a separate process in the data folder, with a time limit and a
memory limit. HARNESS_SANDBOX picks how: "none" is a plain subprocess (unsafe),
"bwrap" is the same inside a bubblewrap sandbox.
"""

import os
import resource
import subprocess
import sys
from pathlib import Path

from harness.tools import MAX_TOOL_OUTPUT, Tool, cap_output

TIMEOUT_SECONDS = 30
MEMORY_LIMIT_BYTES = 1024**3  # 1 GiB
OUT_DIR = "out"  # inside the data folder, so the file tools can read the results
BWRAP = "bwrap"

# One thread for the math libraries. With more, pandas does not even import under the memory limit.
_THREAD_CAPS = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}


def _limit_memory() -> None:
    """Runs in the child just before the script starts."""
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))


def _plain_command(data_dir: Path, code: str) -> list[str]:
    # -I: no PYTHONPATH, no user site-packages, no imports from the current folder.
    return [sys.executable, "-I", "-c", code]


def _bwrap_command(data_dir: Path, code: str) -> list[str]:
    """The same Python call, inside a bubblewrap sandbox. See docs/steps/07-sandbox.md for each flag."""
    python = Path(sys.executable)
    python_root = python.resolve().parents[2]  # the venv's python is a symlink into uv's Python folder
    venv = Path(sys.prefix)
    data = data_dir.resolve()
    # A symlink per data entry, so both legacy/x.xlsx and data/legacy/x.xlsx work. Models write both.
    links = [arg for entry in data.iterdir() for arg in ("--symlink", f"data/{entry.name}", f"/sandbox/{entry.name}")]
    return [
        BWRAP,
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",  # fresh and empty, gone after the run
        "--ro-bind", str(python_root), str(python_root),
        "--ro-bind", str(venv), str(venv),
        "--tmpfs", "/sandbox",
        "--ro-bind", str(data), "/sandbox/data",
        "--bind", str(data / OUT_DIR), f"/sandbox/data/{OUT_DIR}",  # the only writable place
        *links,
        "--remount-ro", "/sandbox",
        "--unshare-all",  # no network, no other processes
        "--die-with-parent",  # the timeout kills bwrap, and the script with it
        "--new-session",  # no access to the terminal
        "--clearenv",
        "--setenv", "HOME", "/tmp",
        *(arg for name, value in _THREAD_CAPS.items() for arg in ("--setenv", name, value)),
        "--chdir", "/sandbox",
        "--",
        str(python), "-I", "-c", code,
    ]


def _sandbox_error(detail: str) -> str:
    return (
        f"Error: the sandbox could not start: {detail}. Install bubblewrap, "
        "or set HARNESS_SANDBOX=none to run scripts without a sandbox (unsafe)."
    )


def _snapshot(out_dir: Path) -> dict[str, tuple[float, int]]:
    """Name -> (mtime, size) of every file in out/, to spot new and changed files."""
    return {p.name: (p.stat().st_mtime, p.stat().st_size) for p in out_dir.iterdir() if p.is_file()}


def run_python(data_dir: Path, code: str, sandbox: str = "bwrap") -> str:
    """Run `code` with the data folder as its working directory. Returns what it printed and wrote."""
    out_dir = data_dir / OUT_DIR
    out_dir.mkdir(exist_ok=True)
    before = _snapshot(out_dir)

    # Fail closed: a typo must not mean "no sandbox".
    if sandbox == "bwrap":
        command = _bwrap_command(data_dir, code)
    elif sandbox == "none":
        command = _plain_command(data_dir, code)
    else:
        raise ValueError(f"unknown sandbox mode {sandbox!r}: use bwrap or none")
    env = {"HOME": os.environ.get("HOME", "/tmp"), "PATH": os.environ.get("PATH", ""), **_THREAD_CAPS}
    try:
        done = subprocess.run(
            command,
            cwd=data_dir,
            env=env,
            capture_output=True,  # reads both pipes, so a chatty script never blocks
            text=True,
            timeout=TIMEOUT_SECONDS,
            preexec_fn=_limit_memory,
        )
        stdout, stderr, code_ = done.stdout, done.stderr, done.returncode
    except FileNotFoundError as e:  # bwrap is not installed
        return _sandbox_error(str(e))
    except subprocess.TimeoutExpired as e:
        partial_out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        note = f"Error: the script ran longer than {TIMEOUT_SECONDS} seconds and was stopped."
        return note + (f"\nOutput before that:\n{cap_output(partial_out, MAX_TOOL_OUTPUT // 2)}" if partial_out else "")

    if sandbox == "bwrap" and code_ != 0 and stderr.startswith("bwrap:"):  # bwrap failed before Python ran
        return _sandbox_error(stderr.strip())

    # Half the output budget each, so the whole result fits under the tool cap.
    parts = []
    if stdout:
        parts.append(cap_output(stdout, MAX_TOOL_OUTPUT // 2).rstrip("\n"))
    if stderr:
        parts.append("[stderr]\n" + cap_output(stderr, MAX_TOOL_OUTPUT // 2).rstrip("\n"))
    if code_ != 0:
        parts.append(f"[exit code {code_}]")
    for name, stat in sorted(_snapshot(out_dir).items()):
        if before.get(name) != stat:
            parts.append(f"[wrote {OUT_DIR}/{name} ({max(1, round(stat[1] / 1024))} KB)]")
    if not parts:
        return "(no output)"
    return "\n".join(parts) + "\n"


def make_code_tools(data_dir: Path, sandbox: str) -> list[Tool]:
    """The run_python tool, or nothing when the sandbox setting is "off"."""
    if sandbox == "off":
        return []

    def run(code: str) -> str:
        # The model chooses only the code. The sandbox mode is fixed here.
        return run_python(data_dir, code, sandbox)

    return [
        Tool(
            name="run_python",
            description=(
                "Run a short Python script over the data folder and get its output. Use it for work that does "
                "not fit in a reply: counting, grouping, de-duplicating, comparing whole files or tables. "
                "pandas, openpyxl, pypdf and sqlite3 are available. The working directory is the data folder: "
                "open files with the same relative paths as the other tools, like legacy/customers_export.xlsx. "
                "Write result files only to out/. Print what you want to see."
            ),
            parameters={
                "type": "object",
                "properties": {"code": {"type": "string", "description": "The Python script to run"}},
                "required": ["code"],
            },
            fn=run,
        )
    ]
