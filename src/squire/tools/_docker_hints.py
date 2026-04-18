"""Helpers for Docker tool error messages."""


def _is_local_docker_backend_failure(message: str) -> bool:
    """True when local Docker CLI cannot run against an engine (missing CLI, down daemon, socket)."""
    if "Command not found: docker" in message:
        return True
    lower = message.lower()
    return (
        "cannot connect to the docker daemon" in lower
        or "is the docker daemon running" in lower
        or "error during connect" in lower
    )


def append_local_docker_error_hint(execution_host: str, message: str) -> str:
    """If Docker failed on local (missing CLI or unreachable daemon), append host-selection hint."""
    if execution_host != "local":
        return message
    if not _is_local_docker_backend_failure(message):
        return message
    try:
        from ._registry import get_registry

        names = list(get_registry().host_names)
    except Exception:
        return (
            f"{message}\nHint: This call used host=local. Start Docker locally or pass host= for a "
            "remote machine where the engine runs."
        )

    remotes = [n for n in names if n != "local"]
    if not remotes:
        return (
            f"{message}\nHint: This call used host=local. Start the Docker daemon (or fix context/"
            "socket) on this machine before Docker tools will work here."
        )

    joined = ", ".join(remotes)
    return (
        f"{message}\nHint: This call used host=local. If containers were listed via docker_ps on "
        f"another host, pass that same host= on pull/inspect/restart. Other configured hosts: {joined}."
    )
