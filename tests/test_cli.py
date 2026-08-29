from agent.cli import build_parser


def test_cli_parser_requires_task():
    args = build_parser().parse_args(["fix the bug", "--workspace", "project"])
    assert args.task == "fix the bug"
    assert args.workspace == "project"
