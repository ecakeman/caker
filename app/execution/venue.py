from __future__ import annotations

from pathlib import Path

import yaml

from app.config import settings
from app.execution.docker_util import (
    DockerError,
    compose_project_name,
    compose_ps_has_running,
    container_exists,
    container_running,
    create_venue_container,
    docker_available,
    pull_image,
    start_container,
    venue_container_name,
)
from app.execution.paths import COMPOSE_FILE


class VenueError(Exception):
    pass


def first_compose_service(compose_path: Path) -> str:
    try:
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise VenueError(f"invalid compose file: {compose_path}") from e
    if not isinstance(data, dict):
        raise VenueError("compose file must be a mapping")
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        raise VenueError("compose file has no services")
    if "dev" in services:
        return "dev"
    return next(iter(services.keys()))


def ensure_venue_container(*, user_id: str, session_id: str, workspace_host: Path) -> str:
    if not settings.sandbox_terminal_enabled:
        raise VenueError("sandbox terminal disabled (SANDBOX_TERMINAL_ENABLED=false)")
    if not docker_available():
        raise VenueError("Docker is not available on this host")

    name = venue_container_name(user_id, session_id)
    image = settings.sandbox_venue_image.strip() or "python:3.12-slim"
    host = str(workspace_host.resolve())

    if container_exists(name):
        if not container_running(name):
            start_container(name)
        return name

    try:
        pull_image(image)
        create_venue_container(name=name, image=image, workspace_host=host)
        start_container(name)
    except DockerError as e:
        raise VenueError(str(e)) from e
    return name


def resolve_terminal_exec(
    *,
    user_id: str,
    session_id: str,
    workspace_host: Path,
) -> list[str]:
    """
    Return docker CLI argv after the binary: e.g. ['exec', '-i', name, 'bash']
    or ['compose', '-f', ..., 'exec', '-i', service, 'bash'].
    """
    compose_path = workspace_host / COMPOSE_FILE
    if compose_path.is_file():
        project = compose_project_name(user_id, session_id)
        if compose_ps_has_running(str(compose_path.resolve()), project):
            service = first_compose_service(compose_path)
            return [
                "compose",
                "-f",
                str(compose_path.resolve()),
                "-p",
                project,
                "exec",
                "-it",
                service,
                "/bin/sh",
            ]

    name = ensure_venue_container(
        user_id=user_id,
        session_id=session_id,
        workspace_host=workspace_host,
    )
    return ["exec", "-it", name, "/bin/sh"]
