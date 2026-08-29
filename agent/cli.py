"""Command-line entry point for the coding agent."""

from __future__ import annotations

import argparse
import sys

from .llm import LLMError, RealLLMClient
from .loop import AgentLoop
from .state import AgentState
from .tools import Toolbox


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ssincha-agent",
        description="Run a bounded coding agent in the current workspace.",
    )
    parser.add_argument("task", help="the programming task for the agent")
    parser.add_argument(
        "--workspace",
        default=".",
        help="workspace directory (defaults to the current directory)",
    )
    return parser


def run_task(task: str, workspace: str = ".") -> AgentState:
    llm = RealLLMClient.from_environment()
    tools = Toolbox(workspace)
    return AgentLoop(llm=llm, tools=tools).run(AgentState(task=task))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        state = run_task(args.task, args.workspace)
    except (LLMError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Task: {state.task}")
    print(f"Steps: {state.step_count}")
    for index, step in enumerate(state.trajectory, start=1):
        status = "ok" if step.success else "failed"
        print(f"[{index}] {step.action.type} ({status})")
        print(step.observation)
    if state.error_logs:
        print("Errors:")
        for error in state.error_logs:
            print(f"- {error.source}: {error.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
