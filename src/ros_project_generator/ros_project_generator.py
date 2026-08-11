#!/usr/bin/env python3

import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from robotics_dockers import DockerContextConfig, generate_docker_context
from robotics_dockers.errors import RoboticsDockersError

from ros_project_generator.logging_utils import create_logger
from ros_project_generator.resource_installer import ResourceInstaller, ResourceSpec
from ros_project_generator.ros_variant import RosVariant
from ros_project_generator.utilities import Utilities
from ros_project_generator.vscode_project_creator import VscodeProjectCreator


class RosProjectCreatorException(Exception):
    """Base exception for all errors related to RosProjectCreator."""


class RosProjectCreator:
    """
    Class to create a ROS project with various configurations and checks.
    """

    # ==========================================================================
    # non-static private methods
    # ==========================================================================

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        ros_distro: str,
        base_img: str,
        image_main_user: Optional[str],
        img_id: Optional[str],
        use_host_nvidia_driver: bool = False,
        use_vscode_project: bool = False,
        use_pre_commit: bool = True,
        use_console_log: bool = True,
        log_file: str = '',
        log_level: str = 'DEBUG',
    ):
        """
        Initializes the RosProjectCreator class.
        Args:
            project_id (str): The ID of the project.
            base_dir (Path): The path where the project will be created.
            ros_distro (str): The ROS distribution to be used.
            base_img (str): Absolute path under the user's home where the project will be created
            img_id (str): The image ID.
            image_main_user (str): Main user for the image.
            use_vscode_project (bool): Whether to create a VS Code project.
            use_pre_commit (bool): Whether to use pre-commit.
            use_console_log (bool): Whether to log to console.
            log_file (str): The file to log to.
            log_level (str): The logging level.
        Raises:
            Exception: If any of the parameters are invalid or if any required files are missing.
        """

        # Logger construction is intentionally outside the try-except block because the
        # exception handler below needs a valid logger to report setup failures.
        self._logger = create_logger(
            name='RosProjectCreator', use_console_log=use_console_log, log_file=log_file, log_level=log_level
        )

        try:
            # Some parameters are required to be non-empty strings.
            # The assert_non_empty method raises an Exception if the condition is not met.
            self._project_id = Utilities.clean_str(project_id)
            Utilities.assert_non_empty(self._project_id, "Project's id must be a non-empty string")

            if project_dir is None:
                raise RosProjectCreatorException('Project directory must be provided')

            project_dir_str = str(project_dir).strip()

            if project_dir_str == '':
                raise RosProjectCreatorException('Project directory must be a non-empty path')

            # Remove leading and trailing whitespace, so paths like
            # "   /home/user/project"    => "/home/user/project" or
            # "/home/user/project   "    => "/home/user/project" or
            # "   /home/user/project   " => "/home/user/project"
            # are accepted. Relative paths, including '.', are resolved before
            # checking that the final destination is inside the active user's home.
            self._project_dir = Path(project_dir_str).expanduser().resolve()

            # Get home of the user who actually invoked the script (even under sudo)
            # When running under sudo, the environment variable SUDO_USER is set to the user who invoked sudo.
            real_user = os.getenv('SUDO_USER') or os.getenv('USER')

            if not real_user:
                raise RosProjectCreatorException('Unable to determine the active user')

            user_home = Path(pwd.getpwnam(real_user).pw_dir).resolve()

            # Ensure project_dir is inside the user's home.
            try:
                self._project_dir.relative_to(user_home)
            except ValueError:
                raise RosProjectCreatorException(
                    f"Error: Project directory is '{str(self._project_dir)}'. Project directory must be inside the "
                    f"home of the active user '{user_home}'"
                ) from None

            # If the project dir already exist, do nothing, print message and exit.
            # The user must decide how to proceed manually (deleting the existing project dir and re-create the project,
            # create the project in a different directory, etc.)
            if self._project_dir.exists():
                raise RosProjectCreatorException(
                    f"Project dir '{str(self._project_dir)}' already exists. "
                    f'Remove it manually or choose a different project directory.'
                )

            self._resources_dir = Path(__file__).parent.joinpath('resources')
            Utilities.assert_dir_existence(self._resources_dir, f"Path '{self._resources_dir.resolve()}' is required")

            ros_variant_yaml_file = self._resources_dir.joinpath('ros', 'ros_variants.yaml')
            self._ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)
            self._assert_ros2_variant()

            self._base_img = Utilities.clean_str(base_img)
            Utilities.assert_non_empty(self._base_img, 'Base image must be a non-empty string')
            base_img_name = str(self._base_img)
            self._base_img = base_img_name

            if not Utilities.is_valid_docker_image_name(base_img_name):
                raise RosProjectCreatorException(
                    f"Base image '{self._base_img}' is not a valid Docker image name. "
                    'Valid names must start with a lowercase letter or number, '
                    'followed by lowercase letters, numbers, underscores, or dashes.'
                )

            self._image_main_user = Utilities.clean_str(image_main_user)
            Utilities.assert_non_empty(self._image_main_user, 'Image user must be a non-empty string')
            image_main_user_name = str(self._image_main_user)
            self._image_main_user = image_main_user_name

            if ' ' in image_main_user_name:
                raise RosProjectCreatorException('Image user must not contain spaces')

            if self._image_main_user == 'root':
                self._image_main_user_home = Path(f'/{self._image_main_user}')
            else:
                self._image_main_user_home = Path(f'/home/{self._image_main_user}')

            self._img_workspace_dir = self._image_main_user_home.joinpath('workspace')
            self._img_datasets_dir = self._image_main_user_home.joinpath('datasets')
            self._img_ssh_dir = self._image_main_user_home.joinpath('.ssh')

            # If img_id is not provided, it is set to the default value.
            self._img_id = Utilities.clean_str(img_id) or f'{self._project_id}:latest'

            if not Utilities.is_valid_docker_image_name(self._img_id):
                raise RosProjectCreatorException(
                    f"Image ID '{self._img_id}' is not a valid Docker image name. "
                    'Valid names must start with a lowercase letter or number, '
                    'followed by lowercase letters, numbers, underscores, or dashes.'
                )

            self._use_host_nvidia_driver = use_host_nvidia_driver
            self._assert_robotics_dockers_supported_user()

            # Check if the git binary exists in the system.
            self._check_git_binary_existence()

            # If the pre-commit argument is True, check if the pre-commit binary exists in the
            # system.
            self._use_pre_commit = use_pre_commit

            if self._use_pre_commit:
                self._check_pre_commit_binary_existence()

            self._logger.info(f"Creating project '{self._project_id}'")

            self._install_items()

            # Create VS Code project if requested.
            if use_vscode_project:
                self._vscode_project_creator = VscodeProjectCreator(
                    self._project_id,
                    self._ros_variant.get_distro(),
                    self._img_id,
                    self._image_main_user,
                    self._image_main_user_home,
                    self._project_dir,
                    self._img_workspace_dir,
                    user_home,
                    self._use_host_nvidia_driver,
                    use_console_log,
                    log_file,
                    log_level,
                )

            self._logger.info(self._initialize_git_repo())

            if use_pre_commit:
                self._logger.info(self._install_pre_commit_config())
        except RosProjectCreatorException as e:
            self._logger.error(f'{e}')
            raise
        except Exception as e:
            self._logger.error(f'{e}')
            raise RosProjectCreatorException(f'{e}') from e

    def _check_git_binary_existence(self) -> None:
        # Check git binary existence.
        if not shutil.which('git'):
            raise RosProjectCreatorException('Git binary not found in the system')

    def _check_pre_commit_binary_existence(self) -> None:
        # Check pre-commit binary existence.
        if not shutil.which('pre-commit'):
            raise RosProjectCreatorException('pre-commit binary not found in the system')

    def _assert_robotics_dockers_supported_user(self) -> None:
        if self._image_main_user == 'root':
            raise RosProjectCreatorException("Image user 'root' is not supported by the ROS 2 Docker generator yet")

    def _assert_ros2_variant(self) -> None:
        if self._ros_variant.get_version() != 2:
            raise RosProjectCreatorException(
                f"ROS distro '{self._ros_variant.get_distro()}' is ROS {self._ros_variant.get_version()}. "
                'ros-project-generator currently supports ROS 2 only.'
            )

    def _create_items_to_install(self) -> None:
        # Relative path to the deps file from the project directory.
        relative_deps_file = Path('deps.repos')

        # Path where the dependency packages will be installed.
        relative_deps_target_dir = Path('src/0_deps')

        self._items_to_install = [
            ResourceSpec.file('.gitignore', 'git/dot_gitignore'),
            ResourceSpec.directory('.gitlab', 'git/gitlab'),
            ResourceSpec.file(str(relative_deps_file), 'deps/deps.repos'),
            ResourceSpec.file('pyproject.toml', 'pyproject.toml'),
            ResourceSpec.template('README.md', 'README.j2', {'project_id': self._project_id}),
            ResourceSpec.file('src/.clang-format', 'clang/dot_clang-format'),
            ResourceSpec.file('src/.clang-tidy', 'clang/dot_clang-tidy'),
            ResourceSpec.directory(str(relative_deps_target_dir)),
            ResourceSpec.template(
                'src/bringup/CMakeLists.txt',
                f'ros/bringup_CMakeLists_ros{self._ros_variant.get_version()}.j2',
                {'c_version': self._ros_variant.get_c_version(), 'cpp_version': self._ros_variant.get_cpp_version()},
            ),
            ResourceSpec.directory('src/bringup/config'),
            ResourceSpec.directory('src/bringup/launch'),
            ResourceSpec.file(
                'src/bringup/package.xml', f'ros/bringup_package_ros{self._ros_variant.get_version()}.xml'
            ),
            ResourceSpec.directory('src/bringup/rviz'),
            ResourceSpec.directory('src/bringup/scripts'),
            ResourceSpec.template(
                'src/simulation/CMakeLists.txt',
                f'ros/simulation_CMakeLists_ros{self._ros_variant.get_version()}.j2',
                {'c_version': self._ros_variant.get_c_version(), 'cpp_version': self._ros_variant.get_cpp_version()},
            ),
            ResourceSpec.directory('src/simulation/config'),
            ResourceSpec.directory('src/simulation/launch'),
            ResourceSpec.file(
                'src/simulation/package.xml', f'ros/simulation_package_ros{self._ros_variant.get_version()}.xml'
            ),
            ResourceSpec.directory('src/simulation/rviz'),
            ResourceSpec.directory('src/simulation/scripts'),
        ]

        if self._use_pre_commit:
            self._items_to_install.append(
                ResourceSpec.file('.pre-commit-config.yaml', 'git/dot_pre-commit-config.yaml')
            )

    def _install_docker_files_with_robotics_dockers(self) -> None:
        docker_dir = self._project_dir.joinpath('docker')

        try:
            self._logger.info(f"Creating ROS 2 Docker files in '{docker_dir}' using robotics_dockers")
            generate_docker_context(
                DockerContextConfig(
                    image_main_user=self._image_main_user,
                    ros_distro=self._ros_variant.get_distro(),
                    img_id=self._img_id,
                    output_dir=docker_dir,
                    base_img=self._base_img,
                    use_host_nvidia_driver=self._use_host_nvidia_driver,
                    meta_title=f'{self._project_id} ROS 2 Docker image',
                    meta_desc=f'Docker image for the {self._project_id} ROS 2 development project',
                    rosdep_packages_dir='../src',
                )
            )
        except RoboticsDockersError as e:
            raise RosProjectCreatorException(f'robotics_dockers failed while creating Docker files: {e}') from e

        generated_compose_file = docker_dir.joinpath('docker-compose-dev.yaml')
        expected_compose_file = docker_dir.joinpath('docker-compose.yaml')

        if generated_compose_file.exists():
            generated_compose_file.replace(expected_compose_file)

    def _initialize_git_repo(self) -> str:
        cmd = ['git', 'init', '--initial-branch=main']
        cwd = self._project_dir
        self._logger.info(f"Executing command '{' '.join(cmd)}' in '{cwd}'")
        result = subprocess.run(
            cmd,
            cwd=str(cwd),  # Convert Path to string
            stdout=subprocess.PIPE,  # Capture standard output to prevent automatic printing to the console
            stderr=subprocess.PIPE,  # Capture standard error output to handle errors programmatically
            text=True,  # Convert output from bytes to a string for easier processing
            check=True,  # Raise a CalledProcessError exception if the command fails (non-zero exit code)
        )

        return result.stdout.strip()  # Return the output of the command, removing any leading/trailing whitespace

    def _install_items(self) -> None:
        self._create_items_to_install()
        self._install_docker_files_with_robotics_dockers()
        ResourceInstaller(
            resources_dir=self._resources_dir,
            target_dir=self._project_dir,
            logger=self._logger,
            exception_type=RosProjectCreatorException,
        ).install(self._items_to_install)

    def _install_pre_commit_config(self) -> str:
        cmd = ['pre-commit', 'install']
        cwd = self._project_dir
        self._logger.info(f"Executing command '{' '.join(cmd)}' in '{cwd}'...")
        result = subprocess.run(
            cmd,
            cwd=str(cwd),  # set the working directory where the command will be executed
            stdout=subprocess.PIPE,  # capture standard output to prevent automatic printing to the console
            stderr=subprocess.PIPE,  # capture standard error output to handle errors programmatically
            text=True,  # convert output from bytes to a string for easier processing
            check=True,  # raise a calledprocesserror exception if the command fails (non-zero exit code)
        )

        return result.stdout.strip()  # return the output of the command, removing any leading/trailing whitespace
