"""Command-line entry point for the coding agent."""

from __future__ import annotations

import argparse
import sys

from .llm import LLMClient, LLMError, RealLLMClient
from .completion import CompletionGate
from .guardrail import Guardrail
from .loop import AgentLoop
from .session import SessionStore
from .state import AgentState
from .tools import Toolbox
from .test_target import TestTargetBinder


EXIT_SUCCESS = 0
EXIT_INCOMPLETE = 1
EXIT_SETUP_ERROR = 2


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
    llm: LLMClient | None = None,
) -> AgentState:
    if reset_session and session is None:
        raise ValueError("--reset-session requires --session")

    tools = Toolbox(workspace)
    store = session_store or SessionStore()
    state = AgentState(task=task)
    completion = CompletionGate()
    test_target_binder = TestTargetBinder(tools.workspace)
    if session is not None:
        if not reset_session:
            session_data = store.load_data(session, tools.workspace)
            state.history.extend(session_data.history)
            completion = CompletionGate.from_snapshot(session_data.completion)
            test_target_binder = TestTargetBinder.from_snapshot(
                tools.workspace, session_data.test_targets
            )
        if state.history:
            state.add_message("user", task)

    client = llm or RealLLMClient.from_environment()
    guardrail = Guardrail(workspace)
    state = AgentLoop(
        llm=client,
        tools=tools,
        guardrail=guardrail,
        completion_gate=completion,
        test_target_binder=test_target_binder,
    ).run(state)
    if session is not None:
        store.save(
            session,
            tools.workspace,
            state.history,
            completion=completion.snapshot(),
            test_targets=test_target_binder.snapshot(),
        )
    return state


def exit_code_for_state(state: AgentState) -> int:
    """Return success only when the loop accepted a final Stop action."""

    if not isinstance(state, AgentState):
        raise ValueError("state must be an AgentState")
    if state.trajectory:
        final_step = state.trajectory[-1]
        if final_step.action.type == "Stop" and final_step.success is True:
            return EXIT_SUCCESS
    return EXIT_INCOMPLETE


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
        return EXIT_SETUP_ERROR

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
    exit_code = exit_code_for_state(state)
    if exit_code != EXIT_SUCCESS:
        print("agent did not complete successfully", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
