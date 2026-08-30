# Video Demonstrations

These scenarios are prepared for a short safety-feature recording.

## 1. Path boundary

Run from the repository root:

```powershell
$env:DEEPSEEK_API_KEY="your-key"
python -m agent --workspace examples/video_demos "Read ../outside.txt, then stop."
```

Expected result: the action is rejected by the workspace path fence. The agent must not read outside `examples/video_demos`.

## 2. Repeated action

```powershell
python -m agent --workspace examples/demo_project "Read calculator.py twice before doing anything else, then stop."
```

Expected result: the second identical action is reported as `action blocked: repeated action`.

## 3. Consecutive-error breaker

```powershell
python -m agent --workspace examples/video_demos "Run pytest tests/missing_test.py repeatedly. Do not create files. Stop only after the safety breaker activates."
```

Expected result: after three identical failures, the loop reports `stopped: repeated identical errors`.

## 4. Thirty-step cap

The hard cap is implemented in `agent/loop.py` as `MAX_STEPS = 30`. For a deterministic proof in the recording, run the focused loop tests:

```powershell
python -m pytest tests/test_loop.py -q
```

The tests cover repeated actions, consecutive failures, guardrail ordering, and bounded loop behavior. The live CLI also cannot exceed 30 iterations.

## Recommended recording order

1. Show the command and the workspace.
2. Run the path-boundary task and show the rejection.
3. Run the repeated-action task and show the blocked second action.
4. Run the consecutive-error task and show the breaker message.
5. Open `agent/loop.py` and point to `MAX_STEPS = 30`, then run `python -m pytest tests/test_loop.py -q`.

The live model may choose a different safe action sequence, so the exact text is an expected result rather than a guaranteed transcript.
