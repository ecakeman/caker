from app.config import settings
from app.execution.docker_util import (
    compose_project_name,
    resolve_pull_image,
    venue_container_name,
)


def test_venue_container_name_short():
    assert venue_container_name("u1", "s1") == "caker-venue-u1-s1"


def test_compose_project_name():
    assert compose_project_name("Sancho", "chat-1") == "caker-sancho-chat-1"


def test_compose_project_name_lowercases_mixed_case():
    name = compose_project_name("Sancho", "chat-e2843a9e-3bc8-482d-9ff5-9ec78a235a51")
    assert name == name.lower()
    assert name.startswith("caker-sancho-")


def test_resolve_pull_image_library(monkeypatch):
    monkeypatch.setattr(
        "app.execution.docker_util.settings.docker_pull_mirror_prefix",
        "docker.m.daocloud.io",
    )
    assert (
        resolve_pull_image("python:3.12-slim")
        == "docker.m.daocloud.io/library/python:3.12-slim"
    )


def test_resolve_pull_image_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.execution.docker_util.settings.docker_pull_mirror_prefix",
        "",
    )
    assert resolve_pull_image("python:3.12-slim") == "python:3.12-slim"
