#!/usr/bin/env python3

from pathlib import Path

from ros_project_generator.logging_utils import create_logger
from ros_project_generator.resource_installer import ResourceInstaller, ResourceSpec
from ros_project_generator.ros_variant import RosVariant
from ros_project_generator.utilities import Utilities


class VscodeProjectCreatorException(Exception):
    """Base exception for all errors related to VscodeProjectCreator."""


class VscodeProjectCreator:
    # ==========================================================================
    # non-static private methods
    # ==========================================================================

    def __init__(
        self,
        project_id: str,
        ros_distro: str,
        img_id: str,
        img_user: str,
        img_user_home: Path,
        workspace_dir: Path,
        img_workspace_dir: Path,
        host_user_home: Path | None = None,
        use_host_nvidia_driver: bool = False,
        use_console_log: bool = True,
        log_file: str = '',
        log_level: str = 'DEBUG',
    ):
        """Creates a new VS Code project based on templates.
        Args:
            ros_distro (str): ROS distro to use (e.g. 'humble')
            img_id (str): ID of the Docker image that VS Code will use to create a container
            img_user (str): User to use inside the container
            img_user_home (Path): Home directory of the user inside the container (e.g. '/home/user')
            workspace_dir (Path): Path to the project directory (e.g. '/path/to/robproj')
            img_workspace_dir (Path): Path to the workspace in the image (e.g. '/home/user/workspaces/robproj')
            use_host_nvidia_driver (bool): If True, use the host's NVIDIA driver. Default is False.
            use_console_log (bool): If True, log to console. Default is True.
            log_file (str): File to log output. Default is "" (no file).
            log_level (str): Logging level. Default is "DEBUG".
        Raises:
            Exception: If any of the arguments are invalid or if the resources directory does not exist.
        """

        # The img_user_home is injected since, even though, usually home paths meet the pattern
        # '/home/<user>', it may not be the case in some images, because it is not a requirement
        # to meet that pattern.

        # Logger construction is intentionally outside the try-except block because the
        # exception handler below needs a valid logger to report setup failures.
        self._logger = create_logger(
            name='VscodeProjectCreator', use_console_log=use_console_log, log_file=log_file, log_level=log_level
        )
        try:
            # Check the resource dir exits.
            self._resources_dir = Path(__file__).parent.joinpath('resources')
            Utilities.assert_dir_existence(self._resources_dir, f"Path '{str(self._resources_dir)}' is required")

            self._project_id = Utilities.clean_str(project_id)
            Utilities.assert_non_empty(self._project_id, 'Project id must be a non-empty string')

            # Get the ros_variant (ros_distro, ros_version, cpp_version, c_version) associated to the passed
            # ros_distro.
            ros_variant_yaml_file = self._resources_dir.joinpath('ros/ros_variants.yaml')
            self._ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)
            self._assert_ros2_variant()

            self._img_id = Utilities.clean_str(img_id)
            Utilities.assert_non_empty(self._img_id, 'Image id must be a non-empty string')

            self._img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(self._img_user, 'Image user must be a non-empty string')

            # The paths on the image side, in the docker-compose file, must be absolute paths.
            # The img_datasets_dir and the img_ssh_dir will be created from the img_user_home path,
            # so we need the img_user_home to be an absolute path.
            if not img_user_home:
                raise VscodeProjectCreatorException('Image user home path must be provided')

            if not img_user_home.is_absolute():
                raise VscodeProjectCreatorException('Image user home path must be an absolute path')

            self._img_user_home = img_user_home

            self._img_datasets_dir = self._img_user_home.joinpath('datasets')
            self._img_ssh_dir = self._img_user_home.joinpath('.ssh')

            # The workspace_dir field cannot be None. It does not matter if it is an absolute or
            # relative path, i.e., as long as the user provides a path. It is the responsibility
            # of the user to provide the path, where the vscode files will be created.
            # If the workspace directory does not exist, it does not matter, it will be created
            # later.
            if not workspace_dir:
                raise VscodeProjectCreatorException('Workspace path must be provided')

            self._workspace_dir = workspace_dir.expanduser().resolve()

            if host_user_home is None:
                self._host_user_home = Path.home().resolve()
            else:
                self._host_user_home = host_user_home.expanduser().resolve()

            try:
                self._host_workspace_relative_to_home = self._workspace_dir.relative_to(self._host_user_home)
            except ValueError:
                raise VscodeProjectCreatorException(
                    f"Workspace path '{self._workspace_dir}' must be inside host user home '{self._host_user_home}' "
                    'to render a portable devcontainer workspace bind mount.'
                ) from None

            if not img_workspace_dir:
                raise VscodeProjectCreatorException('Image workspace path must be provided')

            if not img_workspace_dir.is_absolute():
                raise VscodeProjectCreatorException('Image workspace path must be an absolute path')

            self._img_workspace_dir = img_workspace_dir
            self._use_host_nvidia_driver = use_host_nvidia_driver

            self._install_items()
        except VscodeProjectCreatorException as e:
            self._logger.error(f'{e}')
            raise
        except Exception as e:
            self._logger.error(f'{e}')
            raise VscodeProjectCreatorException(f'{e}') from e

    def _assert_ros2_variant(self) -> None:
        if self._ros_variant.get_version() != 2:
            raise VscodeProjectCreatorException(
                f"ROS distro '{self._ros_variant.get_distro()}' is ROS {self._ros_variant.get_version()}. "
                'ros-project-generator currently supports ROS 2 only.'
            )

    def _create_items_to_install(self) -> None:
        service = 'devcont'

        self._items_to_install = [
            ResourceSpec.template(
                '.devcontainer/devcontainer.json',
                'vscode/devcontainer.json.j2',
                {'service': service, 'remote_user': self._img_user, 'img_workspace_dir': self._img_workspace_dir},
            ),
            ResourceSpec.file('.devcontainer/code-devcont', 'vscode/code-devcont', executable=True),
            ResourceSpec.file('.devcontainer/devcont', 'vscode/devcont', executable=True),
            ResourceSpec.template(
                '.devcontainer/docker-compose.yaml',
                'vscode/docker-compose.yaml.j2',
                {
                    'service': service,
                    'img_id': self._img_id,
                    'use_host_nvidia_driver': self._use_host_nvidia_driver,
                    'host_workspace_relative_to_home': self._host_workspace_relative_to_home,
                    'img_workspace_dir': self._img_workspace_dir,
                    'img_datasets_dir': self._img_datasets_dir,
                    'img_ssh_dir': self._img_ssh_dir,
                    'ros_version': self._ros_variant.get_version(),
                    'ros_distro': self._ros_variant.get_distro(),
                },
                executable=True,
            ),
            ResourceSpec.template(
                '.vscode/c_cpp_properties.json',
                'vscode/c_cpp_properties.json.j2',
                {
                    'c_version': f'c{self._ros_variant.get_c_version()}',
                    'cpp_version': f'c++{self._ros_variant.get_cpp_version()}',
                    'ros_distro': self._ros_variant.get_distro(),
                },
            ),
            ResourceSpec.template('.vscode/tasks.json', 'vscode/tasks.json.j2', {}, executable=True),
            ResourceSpec.template(
                'ws.code-workspace',
                'vscode/ws.code-workspace.j2',
                {
                    'project_id': self._project_id,
                    'ros_distro': self._ros_variant.get_distro(),
                    'python_version': self._ros_variant.get_python_version(),
                },
            ),
        ]

    def _install_items(self) -> None:
        self._create_items_to_install()
        ResourceInstaller(
            resources_dir=self._resources_dir,
            target_dir=self._workspace_dir,
            logger=self._logger,
            exception_type=VscodeProjectCreatorException,
            replace_existing=True,
        ).install(self._items_to_install)
