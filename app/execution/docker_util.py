from __future__ import annotations

import hashlib
import logging
import re
import subprocess

from app.config import settings

logger = logging.getLogger(__name__)

_DOCKER_SLUG_INVALID = re.compile(r"[^a-z0-9_-]+")


class DockerError(Exception):
    """Docker CLI operation failed."""


def _docker_slug(value: str) -> str:
    """Normalize for docker compose -p / container names (lowercase, [a-z0-9_-])."""
    s = value.strip().lower()
    s = _DOCKER_SLUG_INVALID.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-_")
    if not s:
        s = "x"
    if not s[0].isalnum():
        s = f"x{s}"
    return s


def venue_container_name(user_id: str, session_id: str) -> str:
    uid = _docker_slug(user_id)
    sid = _docker_slug(session_id)
    base = f"caker-venue-{uid}-{sid}"
    if len(base) <= 63:
        return base
    digest = hashlib.sha256(f"{user_id}:{session_id}".encode()).hexdigest()[:10]
    return f"caker-venue-{digest}"


def compose_project_name(user_id: str, session_id: str) -> str:
    uid = _docker_slug(user_id)
    sid = _docker_slug(session_id)
    base = f"caker-{uid}-{sid}"
    if len(base) <= 63:
        return base
    digest = hashlib.sha256(f"{user_id}:{session_id}".encode()).hexdigest()[:16]
    return f"caker-{digest}"


def resolve_pull_image(image: str) -> str:
    """Rewrite Docker Hub images via optional mirror prefix (e.g. DaoCloud)."""
    image = image.strip()
    prefix = settings.docker_pull_mirror_prefix.strip().rstrip("/")
    if not prefix:
        return image
    if image.startswith(prefix + "/"):
        return image
    if "/" not in image:
        return f"{prefix}/library/{image}"
    first = image.split("/", 1)[0]
    if "." in first or first in ("localhost", "127.0.0.1"):
        return image
    return f"{prefix}/{image}"


def _docker(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [settings.sandbox_docker_bin, *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise DockerError(
            f"{settings.sandbox_docker_bin} not found; install Docker or set SANDBOX_DOCKER_BIN"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise DockerError(f"docker command timed out: {' '.join(cmd)}") from e


def docker_available() -> bool:
    try:
        proc = _docker(["version", "--format", "{{.Server.Version}}"], timeout=10)
        return proc.returncode == 0
    except DockerError:
        return False


def pull_image(image: str) -> None:
    resolved = resolve_pull_image(image)
    proc = _docker(["pull", resolved], timeout=600)
    if proc.returncode != 0:
        raise DockerError(proc.stderr.strip() or f"docker pull failed for {resolved}")


def container_exists(name: str) -> bool:
    proc = _docker(["inspect", "-f", "{{.Id}}", name], timeout=15)
    return proc.returncode == 0


def container_running(name: str) -> bool:
    proc = _docker(
        ["inspect", "-f", "{{.State.Running}}", name],
        timeout=15,
    )
    return proc.returncode == 0 and (proc.stdout or "").strip().lower() == "true"


def start_container(name: str) -> None:
    proc = _docker(["start", name], timeout=60)
    if proc.returncode != 0:
        raise DockerError(proc.stderr.strip() or f"docker start failed for {name}")


def create_venue_container(
    *,
    name: str,
    image: str,
    workspace_host: str,
) -> None:
    resolved = resolve_pull_image(image)
    args = [
        "create",
        "--name",
        name,
        "--network",
        "bridge",
        "-v",
        f"{workspace_host}:{settings.sandbox_venue_mount}",
        "-w",
        settings.sandbox_venue_mount,
        resolved,
        "sleep",
        "infinity",
    ]
    proc = _docker(args, timeout=120)
    if proc.returncode != 0:
        raise DockerError(proc.stderr.strip() or f"docker create failed for {name}")


def destroy_container(name: str) -> None:
    proc = _docker(["rm", "-f", name], timeout=60)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if "No such container" in err:
            return
        logger.warning("docker rm failed for %s: %s", name, err)


def compose_ps_has_running(compose_file: str, project: str) -> bool:
    proc = _docker(
        [
            "compose",
            "-f",
            compose_file,
            "-p",
            project,
            "ps",
            "-q",
        ],
        timeout=30,
    )
    return proc.returncode == 0 and bool((proc.stdout or "").strip())
