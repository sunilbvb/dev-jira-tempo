import pytest
from tempo_log.completion import generate_completion, get_recent_issues


def test_generate_bash_completion():
    script = generate_completion("bash")
    assert "_tempo_log_completion()" in script
    assert "complete -F _tempo_log_completion tempo-log" in script


def test_generate_zsh_completion():
    script = generate_completion("zsh")
    assert "#compdef tempo-log" in script
    assert "_tempo_log()" in script


def test_generate_fish_completion():
    script = generate_completion("fish")
    assert "complete -c tempo-log" in script


def test_generate_invalid_shell_raises():
    with pytest.raises(ValueError, match="Unsupported shell"):
        generate_completion("powershell")


def test_get_recent_issues():
    # Calling get_recent_issues returns a list without crashing
    issues = get_recent_issues()
    assert isinstance(issues, list)
