"""Tests for Docker tool error hint helper."""

from unittest.mock import MagicMock, patch

from squire.tools._docker_hints import append_local_docker_error_hint


def test_append_hint_non_local_unchanged() -> None:
    msg = "Error: Command not found: docker"
    assert append_local_docker_error_hint("prod-apps-01", msg) == msg


def test_append_hint_no_docker_pattern_unchanged() -> None:
    msg = "Error running docker ps: permission denied"
    assert append_local_docker_error_hint("local", msg) == msg


def test_append_hint_local_only_cli_missing() -> None:
    reg = MagicMock()
    reg.host_names = ["local"]
    with patch("squire.tools._registry.get_registry", return_value=reg):
        msg = "Error: Command not found: docker"
        out = append_local_docker_error_hint("local", msg)
    assert msg in out
    assert "host=local" in out
    assert "daemon" in out.lower() or "socket" in out.lower()


def test_append_hint_daemon_connection_lists_remotes() -> None:
    reg = MagicMock()
    reg.host_names = ["local", "prod-apps-01"]
    with patch("squire.tools._registry.get_registry", return_value=reg):
        msg = (
            "Error: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?\n"
        )
        out = append_local_docker_error_hint("local", msg)
    assert msg in out
    assert "prod-apps-01" in out
    assert "docker_ps" in out


def test_append_hint_lists_remotes_cli_missing() -> None:
    reg = MagicMock()
    reg.host_names = ["local", "prod-apps-01", "lab-02"]
    with patch("squire.tools._registry.get_registry", return_value=reg):
        msg = "Error: Command not found: docker"
        out = append_local_docker_error_hint("local", msg)
    assert "prod-apps-01" in out
    assert "lab-02" in out
    assert "host=" in out
