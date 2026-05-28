---
name: demo-hello
description: Minimal demo skill that runs a hello script under skills/demo-hello/scripts/. Use when testing RunPyScript or skill loading.
allowed-tools: run_py_script
---

# demo-hello

## When to use

User asks for a greeting demo or to verify script execution.

## Instructions

1. Run `run_py_script` with `rel_path="skills/demo-hello/scripts/run.py"`.
2. Report `stdout` to the user if exit code is 0.
