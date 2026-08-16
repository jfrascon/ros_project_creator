import re
from pathlib import Path
from typing import Optional

import yaml


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
            raise ValueError(error_msg)

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
            raise NotADirectoryError(error_msg)

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
            raise FileNotFoundError(error_msg)

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
    def is_valid_docker_image_name(name: str) -> bool:
        """
        Validate a Docker image name according to Docker's official naming rules.

        Format:
            [HOST[:PORT_NUMBER]/]PATH[:TAG]

        See:
            https://docs.docker.com/get-started/docker-concepts/building-images/build-tag-and-publish-an-image/
            #tagging-images
        """

        # Optional registry prefix: host (lower‑case letters, digits, dots, dashes)
        # with optional :PORT, followed by a slash.
        host_and_port_prefix = r'([a-z0-9.-]+(:[0-9]+)?/)?'

        # A separator inside a path component can be:
        #   • a single dot
        #   • one or two underscores
        #   • one or more dashes
        path_separator = r'(?:\.|_{1,2}|-+)'

        # A path component must start and end with an alphanumeric character,
        # separators are allowed only between alphanumerics.
        path_component = rf'[a-z0-9]+(?:{path_separator}[a-z0-9]+)*'

        # PATH = one or more components separated by '/'
        path_re = rf'{path_component}(/{path_component})*'

        # Optional TAG: colon + allowed characters (letters, digits, '_', '.', '-')
        tag_re = r'(:[a-zA-Z0-9_.-]+)?'

        # Full regex combining all parts
        full_re = re.compile(rf'^{host_and_port_prefix}{path_re}{tag_re}$')

        return bool(full_re.match(name))

    @staticmethod
    def load_yaml(file: Path) -> dict:
        try:
            with open(file, 'r') as f:
                content = yaml.safe_load(f)
                return content if isinstance(content, dict) else {}
        except (FileNotFoundError, yaml.YAMLError):
            return {}
