"""A tool that runs a script the model wrote.

Some work does not fit in a reply: counting rows across a whole sheet, comparing five
PDFs with a database, de-duplicating a table. A short script does it in one step and
prints only the answer. The harness runs the script as a separate process, with the data
folder as its working directory, under a time limit and a memory limit.

Two ways to run it, picked by HARNESS_SANDBOX:
- "none": plain subprocess. The script can read and write anything you can. Step 7a.
- "bwrap": the same script inside a bubblewrap sandbox: data read-only, one output
  folder, no network, nothing else of the machine visible. Step 7b.
"""

import os
import resource
import subprocess
import sys
from pathlib import Path

from harness.tools import MAX_TOOL_OUTPUT, Tool, cap_output

TIMEOUT_SECONDS = 30
MEMORY_LIMIT_BYTES = 1024**3  # 1 GiB of address space, enough for pandas on the practice data
OUT_DIR = "out"  # inside the data folder, so the file tools can read what a script wrote
BWRAP = "bwrap"

# Single-threaded math libraries: a sandboxed script has no business starting 20 threads,
# and pandas cannot even import under the memory limit with them.
_THREAD_CAPS = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}


def _limit_memory() -> None:
    """Runs in the child before exec. The limit is inherited by everything the child starts."""
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))


def _plain_command(data_dir: Path, code: str) -> list[str]:
    # -I: isolated. No PYTHONPATH, no user site-packages, and the current folder is not on
    # the import path, so a planted json.py in the data folder is never imported.
    return [sys.executable, "-I", "-c", code]


def _bwrap_command(data_dir: Path, code: str) -> list[str]:
    raise NotImplementedError("the bwrap sandbox comes in step 7b")


def _snapshot(out_dir: Path) -> dict[str, tuple[float, int]]:
    """Name -> (mtime, size) for every file in out/, so new and changed files can be reported."""
    return {p.name: (p.stat().st_mtime, p.stat().st_size) for p in out_dir.iterdir() if p.is_file()}


def run_python(data_dir: Path, code: str, sandbox: str = "bwrap") -> str:
    """Run `code` with the data folder as its working directory. Returns what it printed and wrote."""
    out_dir = data_dir / OUT_DIR
    out_dir.mkdir(exist_ok=True)
    before = _snapshot(out_dir)

    # Fail closed: only the two known modes run anything. A typo must not mean "no sandbox".
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
            capture_output=True,  # both pipes are read, so a chatty script never blocks on a full pipe
            text=True,
            timeout=TIMEOUT_SECONDS,
            preexec_fn=_limit_memory,
        )
        stdout, stderr, code_ = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as e:
        partial_out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        note = f"Error: the script ran longer than {TIMEOUT_SECONDS} seconds and was stopped."
        return note + (f"\nOutput before that:\n{cap_output(partial_out, MAX_TOOL_OUTPUT // 2)}" if partial_out else "")

    # Each stream gets half the tool budget, so the whole result fits and run_tool_call never cuts it again.
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
        # Only `code` is the model's to choose. The sandbox mode is bound here, where the model can't reach it.
        return run_python(data_dir, code, sandbox)

    return [
        Tool(
            name="run_python",
            description=(
                "Run a short Python script over the data folder and get its output. Use it for work that does "
                "not fit in a reply: counting, grouping, de-duplicating, comparing whole files or tables. "
                "pandas, openpyxl, pypdf and sqlite3 are available. The working directory is the data folder: "
                "open files with the same relative paths as the other tools. Write result files only to out/. "
                "Print what you want to see."
            ),
            parameters={
                "type": "object",
                "properties": {"code": {"type": "string", "description": "The Python script to run"}},
                "required": ["code"],
            },
            fn=run,
        )
    ]
