"""Command-line entry point for the coding agent."""

from __future__ import annotations

import argparse
import sys

from .llm import LLMError, RealLLMClient
from .completion import CompletionGate
from .guardrail import Guardrail
from .loop import AgentLoop
from .session import SessionStore
from .state import AgentState
from .tools import Toolbox
from .test_target import TestTargetBinder


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
    parser.add_argument(
        "--session",
        help="local session name to create or continue",
    )
    parser.add_argument(
        "--reset-session",
        action="store_true",
        help="discard saved history before running (requires --session)",
    )
    return parser


def run_task(
    task: str,
    workspace: str = ".",
    *,
    session: str | None = None,
    reset_session: bool = False,
    session_store: SessionStore | None = None,
) -> AgentState:
    if reset_session and session is None:
        raise ValueError("--reset-session requires --session")

    tools = Toolbox(workspace)
    store = session_store or SessionStore()
    state = AgentState(task=task)
    completion = CompletionGate()
    if session is not None:
        if not reset_session:
            session_data = store.load_data(session, tools.workspace)
            state.history.extend(session_data.history)
            completion = CompletionGate.from_snapshot(session_data.completion)
        if state.history:
            state.add_message("user", task)

    llm = RealLLMClient.from_environment()
    guardrail = Guardrail(workspace)
    state = AgentLoop(
        llm=llm,
        tools=tools,
        guardrail=guardrail,
        completion_gate=completion,
        test_target_binder=TestTargetBinder(tools.workspace),
    ).run(state)
    if session is not None:
        store.save(session, tools.workspace, state.history, completion=completion.snapshot())
    return state


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.reset_session and args.session is None:
        parser.error("--reset-session requires --session")
    try:
        state = run_task(
            args.task,
            args.workspace,
            session=args.session,
            reset_session=args.reset_session,
        )
    except (LLMError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.session is not None:
        print(f"Session: {args.session}")
    print(f"Task: {state.task}")
    print(f"Steps: {state.step_count}")
    for index, step in enumerate(state.trajectory, start=1):
        status = "ok" if step.success else "failed"
        print(f"[{index}] {step.action.type} ({status})")
        print(step.observation)
    if state.error_logs:
        print("Errors:")
        for error in state.error_logs:
            details = ""
            if error.category is not None:
                details = f" [{error.category}/{error.error_type or 'unknown'}"
                if error.location is not None:
                    details += f" at {error.location}"
                details += "]"
            print(f"- {error.source}{details}: {error.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
