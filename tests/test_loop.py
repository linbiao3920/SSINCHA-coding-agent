from agent.action import Action
from agent.guardrail import Guardrail
from agent.loop import AgentLoop, ToolResult
from agent.state import AgentState
from agent.test_target import TestTargetBinder
from pathlib import Path


class ScriptedLLM:
    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, _messages):
        return next(self.actions).to_json()


class RecordingTools:
    def __init__(self, result=ToolResult("ok", True)):
        self.calls = []
        self.result = result

    def execute(self, action):
        self.calls.append(action)
        return self.result


class SequenceTools:
    def __init__(self, results):
        self.calls = []
        self.results = iter(results)

    def execute(self, action):
        self.calls.append(action)
        return next(self.results)


class FeedbackAwareLLM:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(list(messages))
        if len(self.calls) == 2 and any(
            "[structured-feedback]" in message.content for message in messages
        ):
            return Action("Read_File", {"path": "main.py"}).to_json()
        if len(self.calls) > 2:
            return Action("Stop", {"reason": "verified"}).to_json()
        return Action("Execute_Test", {"cmd": "pytest test_main.py"}).to_json()


def test_loop_executes_action_then_stops():
    tools = RecordingTools()
    state = AgentLoop(
        ScriptedLLM([Action("Read_File", {"path": "main.py"}), Action("Stop", {"reason": "done"})]),
        tools,
    ).run(AgentState("inspect the project"))
    assert [step.action.type for step in state.trajectory] == ["Read_File", "Stop"]
    assert len(tools.calls) == 1


def test_loop_blocks_repeated_actions_without_reexecuting_them():
    tools = RecordingTools()
    repeated = Action("Read_File", {"path": "main.py"})
    state = AgentLoop(ScriptedLLM([repeated, repeated, Action("Stop", {"reason": "done"})]), tools).run(
        AgentState("inspect the project")
    )
    assert len(tools.calls) == 1
    assert state.trajectory[1].success is False
    assert state.error_logs[-1].source == "repeated_action"


def test_loop_stops_after_three_identical_failures():
    tools = RecordingTools(ToolResult("test failed", False))
    actions = [
        Action("Execute_Test", {"cmd": "pytest tests/test_a.py"}),
        Action("Execute_Test", {"cmd": "pytest tests/test_b.py"}),
        Action("Execute_Test", {"cmd": "pytest tests/test_c.py"}),
    ]
    state = AgentLoop(ScriptedLLM(actions), tools).run(AgentState("run tests"))
    assert len(state.trajectory) == 3
    assert any(error.message == "test failed" for error in state.error_logs)
    assert state.error_logs[-1].source == "breaker"


def test_loop_uses_guardrail_before_tool_execution(tmp_path: Path):
    tools = RecordingTools()
    guardrail = Guardrail(tmp_path)
    state = AgentLoop(
        ScriptedLLM([Action("Read_File", {"path": "../secret.txt"}), Action("Stop", {"reason": "done"})]),
        tools,
        guardrail=guardrail,
    ).run(AgentState("inspect the project"))
    assert len(tools.calls) == 0
    assert state.error_logs[-1].source == "guardrail"


def test_loop_never_exceeds_thirty_steps():
    class CyclingLLM:
        def __init__(self):
            self.index = 0

        def complete(self, _messages):
            action = Action(
                "Read_File" if self.index % 2 == 0 else "Execute_Test",
                {"path": "main.py"} if self.index % 2 == 0 else {"cmd": "pytest --version"},
            )
            self.index += 1
            return action.to_json()

    state = AgentLoop(CyclingLLM(), RecordingTools()).run(AgentState("keep working"))

    assert state.step_count == 30
    assert len(state.trajectory) == 30


def test_stop_is_blocked_until_test_passes_after_write():
    write = Action("Write_File", {"path": "main.py", "content": "x"})
    test = Action("Execute_Test", {"cmd": "pytest"})
    stop = Action("Stop", {"reason": "done"})
    tools = SequenceTools([ToolResult("written", True), ToolResult("passed", True)])

    state = AgentLoop(ScriptedLLM([write, stop, test, stop]), tools).run(AgentState("edit"))

    assert [step.action.type for step in state.trajectory] == [
        "Write_File", "Stop", "Execute_Test", "Stop"
    ]
    assert state.trajectory[1].success is False
    assert state.trajectory[-1].success is True
    assert state.error_logs[-1].source == "completion"


def test_failed_test_also_blocks_stop_until_a_later_test_passes():
    write = Action("Write_File", {"path": "main.py", "content": "x"})
    test = Action("Execute_Test", {"cmd": "pytest"})
    stop = Action("Stop", {"reason": "done"})
    tools = SequenceTools([
        ToolResult("written", True),
        ToolResult("failed", False),
        ToolResult("passed", True),
    ])

    state = AgentLoop(
        ScriptedLLM([write, test, stop, test, stop]),
        tools,
    ).run(AgentState("edit"))

    assert state.trajectory[2].success is False
    assert state.trajectory[-1].success is True
    assert len(tools.calls) == 3


def test_structured_failure_feedback_changes_next_mock_action():
    llm = FeedbackAwareLLM()
    tools = SequenceTools([
        ToolResult(
            'exit_code=1\nstdout:\nE       AssertionError: expected 2, got 1\n'
            'File "tests/test_main.py", line 4\nstderr:\n',
            False,
        ),
        ToolResult("value = 2", True),
    ])

    state = AgentLoop(llm, tools).run(AgentState("fix main"))

    assert [step.action.type for step in state.trajectory] == [
        "Execute_Test", "Read_File", "Stop"
    ]
    assert any("category: assertion" in message.content for message in llm.calls[1])
    assert state.error_logs[0].category == "assertion"
    assert state.error_logs[0].location == "tests/test_main.py:4"


def test_test_target_binding_blocks_unrelated_test_before_execution(tmp_path: Path):
    (tmp_path / "greet.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "test_blackjack.py").write_text(
        "def test_game(): assert True\n", encoding="utf-8"
    )
    (tmp_path / "test_greet.py").write_text(
        "def test_greet(): assert True\n", encoding="utf-8"
    )
    write = Action("Write_File", {"path": "greet.py", "content": "print('date')\n"})
    unrelated = Action("Execute_Test", {"cmd": "pytest test_blackjack.py"})
    focused = Action("Execute_Test", {"cmd": "pytest test_greet.py"})
    stop = Action("Stop", {"reason": "done"})
    tools = RecordingTools()
    llm = ScriptedLLM([write, unrelated, focused, stop])

    state = AgentLoop(
        llm,
        tools,
        test_target_binder=TestTargetBinder(tmp_path),
    ).run(AgentState("update greet"))

    assert len(tools.calls) == 2
    assert state.trajectory[1].success is False
    assert state.error_logs[-1].source == "test_binding"
