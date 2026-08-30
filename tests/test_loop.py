from agent.action import Action
from agent.guardrail import Guardrail
from agent.loop import AgentLoop, ToolResult
from agent.state import AgentState
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


def test_loop_stops_after_three_identical_failures():
    tools = RecordingTools(ToolResult("test failed", False))
    actions = [
        Action("Execute_Test", {"cmd": "pytest tests/test_a.py"}),
        Action("Execute_Test", {"cmd": "pytest tests/test_b.py"}),
        Action("Execute_Test", {"cmd": "pytest tests/test_c.py"}),
    ]
    state = AgentLoop(ScriptedLLM(actions), tools).run(AgentState("run tests"))
    assert len(state.trajectory) == 3
    assert state.error_logs[-1].message == "test failed"


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
