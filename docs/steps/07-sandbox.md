# Step 7: Code execution in a sandbox

Some questions are too big for tools that return text. "How many rows in the legacy export are duplicates?" needs every row compared with every other. With `read_excel` the model pages through 56 rows and compares them in its head, which at step 6 it did not even try: 0 of 5 on both Excel tasks. A 5000-row sheet would be hopeless.

A script does that work in one step and prints one number. Step 7 gives the model a `run_python` tool. 7a runs the script the obvious way and shows why that is dangerous. 7b runs it inside a sandbox. 7c measures the difference with the step 6 evals.

## 7a: `run_python`, the obvious way

### What the tool does

The model sends a script. The harness (`src/harness/code_tools.py`) runs it as a separate Python process and returns:

- what the script printed, then `[stderr]` and the traceback if it crashed, then `[exit code N]` if it did not end cleanly;
- one `[wrote out/name (3 KB)]` line for every file the script created or changed in `out/`.

Three choices that shape how the model uses it:

- **The working directory is the data folder.** The model already knows the path `invoices/INV-2026-0001.pdf` from the file tools. The same path works in a script. No new path rules to learn.
- **Results go to `out/` inside the data folder.** A script can write a CSV there, and the model can read it back with `read_text` or `read_excel` on the next turn. The tool reports every new file, so the model knows it exists.
- **Half the output budget each for stdout and stderr.** A script that prints a whole table gets cut like any other tool result, with the note first. The description tells the model to "print what you want to see", which is one number more often than not.

### The limits that come before any sandbox

A runaway script is the most likely failure, sandbox or not:

- **Time.** `subprocess.run(..., timeout=30)`. The script is killed and the tool says so, with whatever it printed before.
- **Memory.** `RLIMIT_AS` of 1 GiB, set in the child just before it starts (`preexec_fn`). A 2 GiB allocation gets a `MemoryError` in the script, not an out-of-memory kill of Ollama. pandas needs `OPENBLAS_NUM_THREADS=1` to import under that limit, so the tool sets it.
- **No imports from the data folder.** `python -I` (isolated mode) keeps the current folder off the import path. A planted `json.py` in `data/` is never imported.
- **A full pipe never blocks.** `capture_output=True` reads both pipes until the end; the cut happens afterwards.
- **The model picks the script, not the mode.** The tool's only argument is `code`. The sandbox mode is bound in a closure the model cannot reach. The first version used `partial(run_python, data_dir, sandbox=sandbox)`, which left `sandbox` as an overridable keyword: the model could have sent `{"code": ..., "sandbox": "none"}` and switched the sandbox off. A security review caught it; a test now pins it. Never let a model argument reach a security setting.

### The danger

With `HARNESS_SANDBOX=none` the script runs as you, with your rights. Two questions, as asked:

> "Write and run a Python script that prints the names of the first five files in my home folder."

```
[tool] run_python({"code":"import os\n\nhome = os.path.expanduser('~')\nfiles = ..."}) -> .bash_history
agent> The first five files in your home folder are: ...
```

> "Write and run a Python script that creates a file called hello.txt one folder above the data folder."

```
[tool] run_python({"code":"with open('../hello.txt', 'w') as f: pass"}) -> (no output)
agent> The file `hello.txt` has been created in the folder directly above the data folder.
```

It was. The model did exactly what it was asked, and the harness let it. Nothing here is the model misbehaving: the point is that a tool that runs code gives the model every right the harness has. `~/.ssh`, the browser profile, `rm -rf` of a project folder: all one sentence away, by request or by a mistake in a script. Two tests in `tests/test_code_tools.py` pin this hole on purpose (`test_plain_mode_can_read_the_home_folder`, `test_plain_mode_can_write_outside_out`), so that 7b has something to close.

### Files to read

1. `src/harness/code_tools.py`: `run_python`, top to bottom.
2. `tests/test_code_tools.py`: the limits, then the two hole tests at the end.
3. `src/harness/config.py`: `HARNESS_SANDBOX` with its three values.

## 7b: The same scripts in the sandbox

`HARNESS_SANDBOX=bwrap` is the default. The script is the same, the limits are the same, the output format is the same. Only the command changes: Python runs inside a bubblewrap sandbox that shows it what a script needs and nothing else.

### What each flag does

| flag | effect |
|---|---|
| `--ro-bind /usr /usr` plus `/lib`, `/lib64`, `/bin` symlinks | the system: shared libraries, certificates, read-only |
| `--proc /proc`, `--dev /dev` | a process table and devices, as every program expects |
| `--tmpfs /tmp` | a fresh, empty `/tmp` that disappears with the sandbox; `HOME` points here |
| `--ro-bind <python install> <same>` per install root, `--ro-bind <venv> <same>` | the interpreter and the installed packages, read-only, at their real paths. `python_roots()` follows the venv's symlink chain (here: uv's alias folder, then the real install) and mounts only those roots. A root that would be the home folder, or above it, is refused: a review found that the first version guessed the root by counting parent folders, which on another layout could have mounted the whole home folder |
| `--tmpfs /sandbox`, `--ro-bind data/ /sandbox/data` | the practice data, read-only |
| `--bind data/out /sandbox/data/out` | the one writable place. Refused if `data/out` is a symlink, since the bind would follow it |
| `--symlink data/<entry> /sandbox/<entry>` for each top-level entry | so `legacy/x.xlsx` and `data/legacy/x.xlsx` both work (see below) |
| `--remount-ro /sandbox` | the working directory itself is read-only, so a stray `open('x', 'w')` fails |
| `--unshare-all` | own namespaces: no network, no view of other processes, no IPC |
| `--die-with-parent` | when the harness kills `bwrap` at the timeout, the script dies with it |
| `--new-session` | the script cannot reach the terminal the harness runs in |
| `--clearenv`, `--setenv HOME /tmp`, thread caps | no environment leaks in; pandas stays single-threaded |

### The same two questions

> "Write and run a Python script that prints the names of the first five files in my home folder."

The model did not even try. Its reply: "The assistant cannot access the user's home folder. The available tools only provide access to the data folder." That is the tool description doing its job, not the sandbox. Had it tried, the test `test_bwrap_cannot_see_files_in_the_home_folder` says what it would have found: the home folder exists (the venv lives under it) and contains none of your files.

> "Write and run a Python script that creates a file called hello.txt one folder above the data folder."

```
[tool] run_python({"code":"...open(file_path, 'w')..."}) -> [stderr] ... OSError: [Errno 30] Read-only file system
[tool] run_python({"code":"...os.makedirs(...)..."}) -> [stderr] ... Read-only file system
agent> The system's file system is read-only ... Creating files outside this directory isn't permitted.
```

Two tries, then it gave up and said so. Nothing reached the host. `tests/test_code_tools.py` has the same checks as tests: no home files, no writes outside `out/`, no network (`socket.create_connection` fails with "Network is unreachable"), the endless script stopped, pandas reading the practice Excel under the memory limit.

### The path lesson

The first sandbox layout put the script directly in `/sandbox/data`. The model then spent ten tool steps on one question, every one of them with a path like `data/legacy/customers_export.xlsx`: it prefixed `data/` even though the script already ran inside that folder, saw "No such file", and tried another guess. The baseline runs showed the same habit with the file tools. A model's path habits are strong, and a tool that fights them loses.

So the layout changed: the script runs in `/sandbox`, where each top-level entry of the data folder is a symlink into `/sandbox/data`. Now `legacy/x.xlsx` and `data/legacy/x.xlsx` both resolve. The same question after the change:

```
[tool] run_python({"code":"import pandas as pd\n\nfile_path = 'legacy/customers_export.xlsx'\ndf = pd.read_excel(file_path)\ndf.dropna(inplace=True)\nduplicate_count = df.duplicated().sum()\nprint(duplicate_count)"}) -> 3
agent> The script found 3 exact duplicates in the legacy customer export file.
```

One script, the right answer. The description also gained an example path, which the model copied.

### What the sandbox does not cover

- **CPU.** A script can spin for the full 30 seconds. A CPU-time limit (`RLIMIT_CPU`) would stop it sooner.
- **Disk.** `out/` has no size limit; a script can fill it.
- **The kernel.** `bwrap` is only as strong as user namespaces. A kernel bug is a way out. The next level up is a container with its own kernel features, or a VM.
- **Plain mode is still one setting away.** `HARNESS_SANDBOX=none` prints a warning at startup and runs scripts with your rights.

### Files to read

1. `src/harness/code_tools.py`: `_bwrap_command`, one flag per line with its reason.
2. `tests/test_code_tools.py`: the `needs_bwrap` tests, each one an escape that fails.
