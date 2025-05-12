#!/usr/bin/env python3
from pathlib import Path
import re
import shutil
from typing import Callable, Optional
import yaml

from jinja2 import Environment


class Utilities:
    # ==========================================================================
    # static private methods
    # ==========================================================================

    @staticmethod
    def assert_non_empty(item, error_msg: str) -> None:
        """
        Asserts that the given item is not empty.

        This function checks if the provided item is empty. If the item is empty, it raises an Exception with the
        provided error message.

        Args:
            item: The item to check for emptiness. This can be a string, list, dictionary, set, or any other object that
                  can be evaluated as empty.
            error_msg (str): The error message to raise if the item is empty.

        Raises:
            Exception: If the item is empty.
        """
        if not item:  # Covers empty strings, lists, dicts, sets, None, etc.
            raise Exception(error_msg)

    @staticmethod
    def assert_dir_existence(path: Path, error_msg: str) -> None:
        """
        Asserts the existence of a given path.

        Args:
            path (Path): The path to check.
            error_msg (str): The error message to raise if the path does not exist or is not a directory.

        Raises:
            Exception: If the path does not exist or is not a directory.
        """
        if not path.exists() or not path.is_dir():
            raise Exception(error_msg)

    @staticmethod
    def assert_file_existence(file: Path, error_msg: str) -> None:
        """
        Asserts the existence of a file.

        Args:
            file (str): The file to check.
            error_msg (str): The error message to raise if the file does not exist or is not a file.

        Raises:
            Exception: If the file does not exist or is not a file.
        """
        if not file.exists() or not file.is_file():
            raise Exception(error_msg)

    @staticmethod
    def clean_str(string: Optional[str]) -> Optional[str]:
        """
        Cleans a string by removing leading and trailing whitespace.
        If the input string is None, it returns None.
        Args:
            string (str): The string to clean.
        Returns:
            str: The cleaned string or None if the input was None.
        """
        return string.strip() if string is not None else None

    @staticmethod
    def copy_file(src: Path, dst: Path, mode: int, log: Optional[Callable[[str], None]] = None) -> None:
        if log:
            log(f"Creating file '{dst.resolve()}'...")

        shutil.copy(src, dst)
        dst.chmod(mode)

    @staticmethod
    def copy_dir(src: Path, dst: Path, mode: int, log: Optional[Callable[[str], None]] = None) -> None:
        if log:
            log(f"Creating directory '{dst.resolve()}'...")

        shutil.copytree(src, dst, dirs_exist_ok=True)
        dst.chmod(mode)

    @staticmethod
    def install_template(
        jinja_env: Environment,
        template: Path,
        context: dict,
        output_file: Path,
        mode: int,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        if log:
            log(f"Creating file '{output_file.resolve()}'...")

        rendered = Utilities.render_template(jinja_env, template, context)
        Utilities.write_file(rendered, output_file)
        output_file.chmod(mode)

    @staticmethod
    def is_valid_docker_image_name(name: str) -> bool:
        """
        Validate a Docker image name according to Docker's official naming rules.

        Format:
            [HOST[:PORT_NUMBER]/]PATH[:TAG]

        See: https://docs.docker.com/get-started/docker-concepts/building-images/build-tag-and-publish-an-image/#tagging-images
        """

        # Optional registry prefix: host (lower‑case letters, digits, dots, dashes)
        # with optional :PORT, followed by a slash.
        host_and_port_prefix = r"([a-z0-9.-]+(:[0-9]+)?/)?"

        # A separator inside a path component can be:
        #   • a single dot
        #   • one or two underscores
        #   • one or more dashes
        path_separator = r"(?:\.|_{1,2}|-+)"

        # A path component must start and end with an alphanumeric character,
        # separators are allowed only between alphanumerics.
        path_component = rf"[a-z0-9]+(?:{path_separator}[a-z0-9]+)*"

        # PATH = one or more components separated by '/'
        path_re = rf"{path_component}(/{path_component})*"

        # Optional TAG: colon + allowed characters (letters, digits, '_', '.', '-')
        tag_re = r"(:[a-zA-Z0-9_.-]+)?"

        # Full regex combining all parts
        full_re = re.compile(rf"^{host_and_port_prefix}{path_re}{tag_re}$")

        return bool(full_re.match(name))

    @staticmethod
    def load_yaml(file: Path) -> dict:
        try:
            with open(file, "r") as f:
                content = yaml.safe_load(f)
                return content if isinstance(content, dict) else {}
        except (FileNotFoundError, yaml.YAMLError):
            return {}

    @staticmethod
    def mkdir(dir: Path, mode: int, log: Optional[Callable[[str], None]] = None) -> None:
        if log:
            log(f"Creating directory '{dir.resolve()}'...")

        dir.mkdir(parents=True, exist_ok=True)
        dir.chmod(mode)

    @staticmethod
    def read_file(file: Path) -> str:
        """
        Reads the content of a file and returns it as a string.

        Args:
            file (Path): The path to the file to be read.

        Returns:
            str: The content of the file.

        Raises:
            Exception: If the file does not exist or is a directory.
        """
        if not file.exists():
            raise Exception(f"File '{file}' does not exist")
        if file.is_dir():
            raise Exception(f"Path '{file}' is a directory, not a file")

        with file.open("r") as f:
            text = f.read()

        return text

    @staticmethod
    def render_template(jinja_env: Environment, template: Path, context: dict) -> str:
        jinja_template = jinja_env.get_template(template.name)
        return jinja_template.render(context)

    @staticmethod
    def write_file(text: str, file: Path) -> None:
        """
        Writes the given text to a specified file.

        Args:
            text (str): The text content to be written to the file.
            file (Path): The path to the file where the text will be written.

        Returns:
            None

        Raises:
            Exception: If the file already exists.
        """
        if file.exists():
            raise Exception(f"File '{file}' already exists")

        with file.open("w") as f:
            f.write(text)
