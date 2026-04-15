from __future__ import annotations

from dataclasses import dataclass
import subprocess


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class ProcessExecutionError(RuntimeError):
    pass


def run_command(args: list[str], *, input_text: str | None = None) -> CommandResult:
    completed = subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ProcessExecutionError(
            f"Command failed ({completed.returncode}): {' '.join(args)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def run_bash(command: str) -> CommandResult:
    completed = subprocess.run(
        ["/bin/bash", "-lc", command],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ProcessExecutionError(
            f"Bash command failed ({completed.returncode}): {command}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )

