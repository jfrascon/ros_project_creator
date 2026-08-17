import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from robotics_dockers import DockerContextConfig, DockerContextResult, generate_docker_context
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
        img_id: Optional[str] = None,
        base_img: Optional[str] = None,
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
            project_dir (Path): The path where the project will be created.
            ros_distro (str): The ROS distribution to be used.
            img_id (str): The image ID, or None to derive it from the project ID.
            base_img (str): Optional Docker base image. robotics_dockers chooses the
                Ubuntu version associated with the ROS distribution when omitted.
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

            if not Utilities.is_valid_project_id(self._project_id):
                raise RosProjectCreatorException(
                    'Project id must start with a lowercase letter or digit and contain only '
                    f"lowercase letters, digits, '-' and '_'; found '{self._project_id}'"
                )

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

            # If img_id is not provided, it is set to the default value.
            self._img_id = Utilities.clean_str(img_id) or f'{self._project_id}:latest'

            self._use_host_nvidia_driver = use_host_nvidia_driver
            self._use_vscode_project = use_vscode_project

            # Check if the git binary exists in the system.
            self._check_git_binary_existence()

            # If the pre-commit argument is True, check if the pre-commit binary exists in the
            # system.
            self._use_pre_commit = use_pre_commit

            if self._use_pre_commit:
                self._check_pre_commit_binary_existence()

            self._logger.info(f"Creating project '{self._project_id}'")

            docker_result = self._install_items()

            # Create VS Code project if requested.
            if self._use_vscode_project:
                self._vscode_project_creator = VscodeProjectCreator(
                    project_id=self._project_id,
                    ros_distro=self._ros_variant.get_distro(),
                    workspace_dir=self._project_dir,
                    source_compose_file=docker_result.context_dir.joinpath('compose_files/docker-compose.yaml'),
                    use_console_log=use_console_log,
                    log_file=log_file,
                    log_level=log_level,
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
            ResourceSpec.template(
                'docker/compose_files/docker-compose.yaml',
                'docker/docker-compose.yaml.j2',
                {
                    'project_id': self._project_id,
                    'service': f'{self._img_id.replace(":", "_").replace("/", "_")}_cont',
                    'img_id': self._img_id,
                    'img_workspace_dir': '/workspace',
                    'img_datasets_dir': '/datasets',
                    'use_host_nvidia_driver': self._use_host_nvidia_driver,
                },
            ),
            ResourceSpec.file('pyproject.toml', 'pyproject.toml'),
            ResourceSpec.template(
                'README.md',
                'README.j2',
                {'project_id': self._project_id, 'img_id': self._img_id, 'ros_distro': self._ros_variant.get_distro()},
            ),
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

    def _install_docker_files_with_robotics_dockers(self) -> DockerContextResult:
        docker_dir = self._project_dir.joinpath('docker')

        try:
            self._logger.info(f"Creating ROS 2 Docker files in '{docker_dir}' using robotics_dockers")
            return generate_docker_context(
                DockerContextConfig(
                    ros_distro=self._ros_variant.get_distro(),
                    img_id=self._img_id,
                    output_dir=docker_dir,
                    base_img=self._base_img,
                    use_host_nvidia_driver=self._use_host_nvidia_driver,
                    # ros_project_generator owns its production and development
                    # Compose files. The default robotics_dockers API therefore
                    # supplies only the image build context in this integration.
                    meta_title=f'{self._project_id} ROS 2 Docker image',
                    meta_desc=f'Docker image for the {self._project_id} ROS 2 development project',
                    rosdep_packages_dir='../src',
                )
            )
        except RoboticsDockersError as e:
            raise RosProjectCreatorException(f'robotics_dockers failed while creating Docker files: {e}') from e

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

    def _install_items(self) -> DockerContextResult:
        self._create_items_to_install()
        docker_result = self._install_docker_files_with_robotics_dockers()
        ResourceInstaller(
            resources_dir=self._resources_dir,
            target_dir=self._project_dir,
            logger=self._logger,
            exception_type=RosProjectCreatorException,
        ).install(self._items_to_install)
        return docker_result

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
