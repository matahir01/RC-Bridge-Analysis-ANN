from rc_bridge.application.cli import main
from rc_bridge.application.project_io import save_project
from rc_bridge.core.models import ProjectInput


def test_cli_new_and_summary(tmp_path, capsys) -> None:
    path = tmp_path / "new_bridge.json"
    assert main(["new", str(path)]) == 0
    assert path.exists()

    capsys.readouterr()
    assert main(["summary", str(path)]) == 0
    output = capsys.readouterr().out
    assert "15 m RC Girder Benchmark" in output
    assert "Physical girder profile: undefined" in output


def test_cli_summary_reads_validated_project(tmp_path, capsys) -> None:
    path = save_project(ProjectInput(name="CLI project"), tmp_path / "cli.json")
    assert main(["summary", str(path)]) == 0
    assert "CLI project" in capsys.readouterr().out
