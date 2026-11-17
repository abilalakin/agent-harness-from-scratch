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
