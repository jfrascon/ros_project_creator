import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from jinja2 import Environment, FileSystemLoader


@dataclass(frozen=True)
class ResourceSpec:
    """Describe one project resource that must be created from the package resources."""

    destination: str
    kind: str
    source: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    executable: bool = False

    @classmethod
    def directory(cls, destination: str, source: Optional[str] = None) -> 'ResourceSpec':
        return cls(destination=destination, kind='directory', source=source)

    @classmethod
    def file(cls, destination: str, source: str, executable: bool = False) -> 'ResourceSpec':
        return cls(destination=destination, kind='file', source=source, executable=executable)

    @classmethod
    def template(
        cls, destination: str, source: str, context: Optional[dict[str, Any]] = None, executable: bool = False
    ) -> 'ResourceSpec':
        return cls(
            destination=destination, kind='template', source=source, context=context or {}, executable=executable
        )


@dataclass(frozen=True)
class ResourceInstaller:
    """Install ResourceSpec entries into a target directory."""

    resources_dir: Path
    target_dir: Path
    logger: logging.Logger
    exception_type: type[Exception] = Exception
    replace_existing: bool = False
    executable_mode: int = field(default=0o775, init=False)
    file_mode: int = field(default=0o664, init=False)

    def install(self, resources: Iterable[ResourceSpec]) -> None:
        for resource in sorted(resources, key=lambda item: item.destination):
            self._install_resource(resource)

    def _install_resource(self, resource: ResourceSpec) -> None:
        destination = Path(resource.destination)
        if destination.is_absolute():
            raise self.exception_type(f"Resource destination '{resource.destination}' must be relative.")

        dst_path = self.target_dir.joinpath(destination)
        src_path = self._resolve_source(resource)

        if self.replace_existing:
            self._remove_existing_destination(dst_path)

        if resource.kind == 'directory':
            self._install_directory(src_path, dst_path)
        elif resource.kind == 'file':
            self._install_file(resource, src_path, dst_path)
        elif resource.kind == 'template':
            self._install_template(resource, src_path, dst_path)
        else:
            raise self.exception_type(f"Unsupported resource kind '{resource.kind}' for '{resource.destination}'.")

    def _install_directory(self, src_path: Optional[Path], dst_path: Path) -> None:
        self.logger.info(f"Creating directory '{dst_path}'")

        if src_path is None:
            dst_path.mkdir(parents=True)
            return

        if not src_path.is_dir():
            raise self.exception_type(f"Required resource '{src_path}' is not a directory.")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_path, dst_path, copy_function=shutil.copy2)
        dst_path.chmod(self.executable_mode)

    def _install_file(self, resource: ResourceSpec, src_path: Optional[Path], dst_path: Path) -> None:
        self.logger.info(f"Creating file '{dst_path}'")

        if src_path is None:
            raise self.exception_type(f"File source is required for resource '{resource.destination}'.")

        if not src_path.is_file():
            raise self.exception_type(f"Required resource '{src_path}' is not a file.")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        self._chmod_file(dst_path, resource.executable)

    def _install_template(self, resource: ResourceSpec, src_path: Optional[Path], dst_path: Path) -> None:
        self.logger.info(f"Creating file '{dst_path}'")

        if src_path is None:
            raise self.exception_type(f"Template source is required for resource '{resource.destination}'.")

        if not src_path.is_file():
            raise self.exception_type(f"Required resource '{src_path}' is not a file.")

        if not isinstance(resource.context, dict):
            raise self.exception_type(
                f"Context for Jinja2 rendering must be a dictionary for resource '{resource.destination}'."
            )

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        jinja2_env = Environment(loader=FileSystemLoader(src_path.parent), trim_blocks=True, lstrip_blocks=True)
        jinja2_template = jinja2_env.get_template(src_path.name)
        dst_path.write_text(jinja2_template.render(resource.context))
        self._chmod_file(dst_path, resource.executable)

    def _chmod_file(self, path: Path, executable: bool) -> None:
        path.chmod(self.executable_mode if executable else self.file_mode)

    def _remove_existing_destination(self, dst_path: Path) -> None:
        if dst_path.is_file():
            dst_path.unlink()
        elif dst_path.is_dir():
            dst_path.rmdir()

    def _resolve_source(self, resource: ResourceSpec) -> Optional[Path]:
        if resource.source is None:
            return None

        src_path = self.resources_dir.joinpath(resource.source)
        if not src_path.exists():
            raise self.exception_type(f"Required resource '{src_path}' does not exist.")

        return src_path
