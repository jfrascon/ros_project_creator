#!/usr/bin/env python3


class DockerPlaform:
    def __init__(self, id: str, architectures: list[str], description: str):
        self._id = id
        self._architectures = architectures
        self._description = description

    def get_id(self) -> str:
        return self._id

    def get_architectures(self) -> list[str]:
        return self._architectures

    def get_description(self) -> str:
        return self._description
