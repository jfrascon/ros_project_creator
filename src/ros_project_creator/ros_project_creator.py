#!/usr/bin/env python3

from pathlib import Path
import pwd
import os
import platform
import shutil
import subprocess
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from ros_project_creator.colorizedlogs import ColorizedLogger
from ros_project_creator.docker_platform import DockerPlaform
from ros_project_creator.ros_variant import RosVariant
from ros_project_creator.utilities import Utilities
from ros_project_creator.vscode_project_creator import VscodeProjectCreator


class RosProjectCreatorException(Exception):
    """Base exception for all errors related to RosProjectCreator."""

    pass


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
        supported_docker_platforms: dict[str, DockerPlaform],
        docker_platform: str,
        img_id: Optional[str],
        img_user: Optional[str],
        use_vscode_project: bool = False,
        use_pre_commit: bool = True,
        use_console_log: bool = True,
        log_file: str = "",
        log_level: str = "DEBUG",
    ):
        """
        Initializes the RosProjectCreator class.
        Args:
            project_id (str): The ID of the project.
            base_dir (Path): The path where the project will be created.
            ros_distro (str): The ROS distribution to be used.
            base_img (str): Absolute path under the user's home where the project will be created
            supported_docker_platforms (list[DockerPlaform]): List of supported Docker platforms.
            docker_platform (str): The Docker platform to be used.
            img_id (str): The image ID.
            img_user (str): The active user for the image.
            use_vscode_project (bool): Whether to create a VSCode project.
            use_pre_commit (bool): Whether to use pre-commit.
            use_console_log (bool): Whether to log to console.
            log_file (str): The file to log to.
            log_level (str): The logging level.
        Raises:
            Exception: If any of the parameters are invalid or if any required files are missing.
        """
        # The constructor may raise an Exception. It is not wrapped in a try-except block
        # because the exception handler logs the error. However, if the logger's construction
        # fails, logging statements cannot be executed.
        self._logger = ColorizedLogger(
            name="RosProjectCreator", use_console_log=use_console_log, log_file=log_file, log_level=log_level
        )

        try:
            # Some parameters are required to be non-empty strings.
            # The assert_non_empty method raises an Exception if the condition is not met.
            self._project_id = Utilities.clean_str(project_id)
            Utilities.assert_non_empty(self._project_id, "Project's id must be a non-empty string")

            if project_dir is None:
                raise RosProjectCreatorException("Project directory must be provided")

            # Convert Path to string to verify it isn't all spaces.
            project_dir_str = str(project_dir)

            # Only reject if the full string is whitespace
            if project_dir_str != "" and project_dir_str.strip() == "":
                raise RosProjectCreatorException("Project directory cannot consist only of whitespace characters")

            # Remove leading and trailing whitespace, so paths like
            # "   /home/user/project" => "/home/user/project" or
            # "/home/user/project   " => "/home/user/project"
            # or "   /home/user/project   " => "/home/user/project"
            # are accepted.
            self._project_dir = Path(project_dir_str.strip()).expanduser().resolve()

            # Get home of the user who actually invoked the script (even under sudo)
            # When running under sudo, the environment variable SUDO_USER is set to the user who invoked sudo.
            real_user = os.getenv("SUDO_USER") or os.getenv("USER")

            if not real_user:
                raise RosProjectCreatorException("Unable to determine the active user")

            user_home = Path(pwd.getpwnam(real_user).pw_dir).resolve()

            # Ensure base_dir is inside the user's home
            try:
                self._project_dir.relative_to(user_home)
            except ValueError:
                raise RosProjectCreatorException(
                    f"Error: Project directory is '{self._project_dir.resolve()}'. Project directory must be inside the home of the active user '{user_home}'"
                )

            # If the project dir already exist, do nothing, print message and exit.
            # The user must decide how to proceed manually (deleting the existing project dir and re-create the project,
            # create the project in a differente directory, etc.)
            # etc.)
            if self._project_dir.exists():
                raise RosProjectCreatorException(
                    f"Project dir '{self._project_dir.resolve()}' already exists. "
                    f"Remove it manually or choose a different project directory."
                )

            self._resources_dir = Path(__file__).parent.joinpath("resources")
            Utilities.assert_dir_existence(self._resources_dir, f"Path '{self._resources_dir.resolve()}' is required")

            ros_variant_yaml_file = self._resources_dir.joinpath("ros", "ros_variants.yaml")
            self._ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)

            self._base_img = Utilities.clean_str(base_img)
            Utilities.assert_non_empty(self._base_img, "Base image must be a non-empty string")

            if not Utilities.is_valid_docker_image_name(self._base_img):
                raise RosProjectCreatorException(
                    f"Base image '{self._base_img}' is not a valid Docker image name. "
                    "Valid names must start with a lowercase letter or number, "
                    "followed by lowercase letters, numbers, underscores, or dashes."
                )

            Utilities.assert_non_empty(supported_docker_platforms, "Supported platforms must be a non-empty list")
            self._supported_docker_platforms = supported_docker_platforms

            self._docker_platform = Utilities.clean_str(docker_platform)

            # If no platform is provided, use the default one associated to the architecture of the machine where this
            # script runs.
            if not self._docker_platform:
                architecture = platform.machine()

                for docker_platform_id, docker_platform_object in self._supported_docker_platforms.items():
                    if architecture in docker_platform_object.get_architectures():
                        self._docker_platform = docker_platform_object.get_id()

                if not self._docker_platform:
                    supported_architectures = "\n".join(
                        [
                            f"Architectures: {', '.join(docker_platform.get_architectures())} // Docker platform: {docker_platform.get_id()}"
                            for docker_platform in self._supported_docker_platforms.values()
                        ]
                    )

                    raise RosProjectCreatorException(
                        f"Architecture '{architecture}' is not supported.\nSupported architectures and Docker platforms are:\n{supported_architectures}"
                    )

            if self._docker_platform not in self._supported_docker_platforms:
                supported_docker_platforms_str = ", ".join(self._supported_docker_platforms.keys())

                raise RosProjectCreatorException(
                    f"Platform '{self._docker_platform}' is not supported.\nSupported Docker platforms are: {supported_docker_platforms_str}"
                )

            # If img_is is not provided, it is set to the default value.
            self._img_id = Utilities.clean_str(img_id) or f"{self._project_id}:latest"

            if not Utilities.is_valid_docker_image_name(self._img_id):
                raise RosProjectCreatorException(
                    f"Image ID '{self._img_id}' is not a valid Docker image name. "
                    "Valid names must start with a lowercase letter or number, "
                    "followed by lowercase letters, numbers, underscores, or dashes."
                )

            self._img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(self._img_user, "Image user must be a non-empty string")

            if self._img_user == "root":
                self._img_user_home = Path(f"/{self._img_user}")
            else:
                self._img_user_home = Path(f"/home/{self._img_user}")

            self._img_workspace_dir = self._img_user_home.joinpath("workspace")
            self._img_datasets_dir = self._img_user_home.joinpath("datasets")
            self._img_gitconfig_dir = self._img_user_home.joinpath(".gitconfig")
            self._img_ssh_dir = self._img_user_home.joinpath(".ssh")
            self._img_entrypoint = self._img_user_home.joinpath("entrypoint.sh")

            # Create VSCode project if requested.
            if use_vscode_project:
                self._vscode_project_creator = VscodeProjectCreator(
                    self._ros_variant.get_distro(),
                    self._img_id,
                    self._img_user,
                    self._project_dir,
                    self._img_workspace_dir,
                    use_console_log,
                    log_file,
                    log_level,
                )
            else:
                self._vscode_project_creator = None

            self._check_templates_existance(use_pre_commit)

            self._check_git_binary_existance()

            if use_pre_commit:
                self._check_pre_commit_binary_existance()
        except RosProjectCreatorException as e:
            self._logger.error(f"{e}")
            raise

    def _check_git_binary_existance(self) -> None:
        # Check git binary existence.
        if not shutil.which("git"):
            raise RosProjectCreatorException("Git binary not found in the system")

    def _check_pre_commit_binary_existance(self) -> None:
        # Check pre-commit binary existence.
        if not shutil.which("pre-commit"):
            raise RosProjectCreatorException("pre-commit binary not found in the system")

    def _check_templates_existance(self, use_pre_commit: bool) -> None:
        # Check existance of Docker templates.
        # ------------------------------------
        self._docker_templates_dir = self._resources_dir.joinpath("docker")
        Utilities.assert_dir_existence(
            self._docker_templates_dir, f"Directory '{self._docker_templates_dir.resolve()}' is required"
        )

        self._build_img_template = self._docker_templates_dir.joinpath("build_img.j2")
        Utilities.assert_file_existence(
            self._build_img_template, f"Template '{self._build_img_template.resolve()}' is required"
        )

        self._dockerfile_template = self._docker_templates_dir.joinpath("Dockerfile")
        Utilities.assert_file_existence(
            self._dockerfile_template, f"Template '{self._dockerfile_template.resolve()}' is required"
        )

        self._dockerignore_template = self._docker_templates_dir.joinpath("dot_dockerignore")
        Utilities.assert_file_existence(
            self._dockerignore_template, f"Template '{self._dockerignore_template.resolve()}' is required"
        )

        self._docker_compose_template = self._docker_templates_dir.joinpath("docker-compose.j2")
        Utilities.assert_file_existence(
            self._docker_compose_template,
            f"Template '{self._docker_compose_template.resolve()}' is required",
        )

        self._entrypoint_template = self._docker_templates_dir.joinpath("entrypoint.sh")
        Utilities.assert_file_existence(
            self._entrypoint_template, f"Template '{self._entrypoint_template.resolve()}' is required"
        )

        self._root_environment_template = None

        if self._img_user != "root":
            self._root_environment_template = self._docker_templates_dir.joinpath(f"environment_root.sh")
            Utilities.assert_file_existence(
                self._root_environment_template, f"Template '{self._root_environment_template.resolve()}' is required"
            )

        # Check script templates
        self._scripts_templates_dir = self._resources_dir.joinpath("scripts")

        self._deduplicate_path_template = self._scripts_templates_dir.joinpath("deduplicate_path.sh")
        Utilities.assert_file_existence(
            self._deduplicate_path_template,
            f"Template '{self._deduplicate_path_template.resolve()}' is required",
        )

        self._dot_bash_aliases_template = self._scripts_templates_dir.joinpath("dot_bash_aliases")
        Utilities.assert_file_existence(
            self._dot_bash_aliases_template,
            f"Template '{self._dot_bash_aliases_template.resolve()}' is required",
        )

        self._install_core_template = self._scripts_templates_dir.joinpath("install_core.sh")
        Utilities.assert_file_existence(
            self._install_core_template,
            f"Template '{self._install_core_template.resolve()}' is required",
        )

        if self._ros_variant.get_ubuntu_version() == "20.04":
            self._install_mesa_packages_template = self._scripts_templates_dir.joinpath(
                "install_kisak_mesa_packages.sh"
            )
        else:
            self._install_mesa_packages_template = self._scripts_templates_dir.joinpath(
                "install_default_mesa_packages.sh"
            )

        Utilities.assert_file_existence(
            self._install_mesa_packages_template,
            f"Template '{self._install_mesa_packages_template.resolve()}' is required",
        )

        # Check existance of ROS templates
        # --------------------------------
        self._ros_templates_dir = self._resources_dir.joinpath("ros")
        Utilities.assert_dir_existence(
            self._ros_templates_dir, f"Directory '{self._ros_templates_dir.resolve()}' is required"
        )

        self._install_ros_template = self._ros_templates_dir.joinpath("install_ros.j2")
        Utilities.assert_file_existence(
            self._install_ros_template, f"Template '{self._install_ros_template.resolve()}' is required"
        )

        self._ros_packages_template = self._ros_templates_dir.joinpath(
            f"packages_ros{self._ros_variant.get_version()}.txt"
        )
        Utilities.assert_file_existence(
            self._ros_packages_template, f"Template '{self._ros_packages_template.resolve()}' is required"
        )

        self._environment_template = self._ros_templates_dir.joinpath(
            f"environment_ros{self._ros_variant.get_version()}.j2"
        )
        Utilities.assert_file_existence(
            self._environment_template, f"Template '{self._environment_template.resolve()}' is required"
        )

        self._rosdep_init_update_template = self._ros_templates_dir.joinpath("rosdep_init_update.sh")
        Utilities.assert_file_existence(
            self._rosdep_init_update_template, f"Template '{self._rosdep_init_update_template.resolve()}' is required"
        )

        self._rosbuild_template = self._ros_templates_dir.joinpath(f"ros{self._ros_variant.get_version()}build.sh")
        Utilities.assert_file_existence(
            self._rosbuild_template, f"Template '{self._rosbuild_template.resolve()}' is required"
        )

        self._rosdep_ignored_key_template = None
        self._colcon_mixin_metadata_template = None
        self._catkin_config_template = None

        if self._ros_variant.get_version() == 1:
            self._catkin_config_template = self._ros_templates_dir.joinpath("catkin_config_ros1.yaml")
            Utilities.assert_file_existence(
                self._catkin_config_template, f"Template '{self._catkin_config_template.resolve()}' is required"
            )
        elif self._ros_variant.get_version() == 2:
            self._rosdep_ignored_key_template = self._ros_templates_dir.joinpath(
                f"rosdep_ignored_keys_ros{self._ros_variant.get_version()}.yaml"
            )
            Utilities.assert_file_existence(
                self._rosdep_ignored_key_template,
                f"Template '{self._rosdep_ignored_key_template.resolve()}' is required",
            )

            self._colcon_mixin_metadata_template = self._ros_templates_dir.joinpath(f"colcon_mixin_metadata.sh")
            Utilities.assert_file_existence(
                self._colcon_mixin_metadata_template,
                f"Template '{self._colcon_mixin_metadata_template.resolve()}' is required",
            )
        else:
            raise RosProjectCreatorException(
                f"ROS version '{self._ros_variant.get_version()}' is not supported. Supported versions are 1 and 2"
            )

        self._bringup_cmakelists_template = self._ros_templates_dir.joinpath(
            f"bringup_CMakeLists_ros{self._ros_variant.get_version()}.j2"
        )
        Utilities.assert_file_existence(
            self._bringup_cmakelists_template, f"Template '{self._bringup_cmakelists_template.resolve()}' is required"
        )

        self._bringup_package_template = self._ros_templates_dir.joinpath(
            f"bringup_package_ros{self._ros_variant.get_version()}.xml"
        )
        Utilities.assert_file_existence(
            self._bringup_package_template, f"Template '{self._bringup_package_template.resolve()}' is required"
        )

        self._simulation_cmakelists_template = self._ros_templates_dir.joinpath(
            f"simulation_CMakeLists_ros{self._ros_variant.get_version()}.j2"
        )
        Utilities.assert_file_existence(
            self._simulation_cmakelists_template,
            f"Template '{self._simulation_cmakelists_template.resolve()}' is required",
        )

        self._simulation_package_template = self._ros_templates_dir.joinpath(
            f"simulation_package_ros{self._ros_variant.get_version()}.xml"
        )
        Utilities.assert_file_existence(
            self._simulation_package_template, f"Template '{self._simulation_package_template.resolve()}' is required"
        )

        # Check existance of Git templates.
        # ---------------------------------
        git_templates_dir = self._resources_dir.joinpath("git")
        Utilities.assert_dir_existence(git_templates_dir, f"Directory '{git_templates_dir.resolve()}' is required")

        self._gitlab_templates_src_dir = git_templates_dir.joinpath("gitlab")
        Utilities.assert_dir_existence(
            self._gitlab_templates_src_dir, f"Directory '{self._gitlab_templates_src_dir.resolve()}' is required"
        )

        self._gitignore_template = git_templates_dir.joinpath("dot_gitignore")
        Utilities.assert_file_existence(
            self._gitignore_template, f"Template '{self._gitignore_template.resolve()}' is required"
        )

        if use_pre_commit:
            self._pre_commit_template = git_templates_dir.joinpath("dot_pre-commit-config.yaml")
            Utilities.assert_file_existence(
                self._pre_commit_template, f"Template '{self._pre_commit_template.resolve()}' is required"
            )
        else:
            self._pre_commit_template = None

        # Check existance of clang templates
        # ----------------------------------
        self._clang_templates_dir = self._resources_dir.joinpath("clang")
        Utilities.assert_dir_existence(
            self._clang_templates_dir, f"Directory '{self._clang_templates_dir.resolve()}' is required"
        )

        self._clang_format_template = self._clang_templates_dir.joinpath("dot_clang-format")
        Utilities.assert_file_existence(
            self._clang_format_template, f"Template '{self._clang_format_template.resolve()}' is required"
        )

        self._clang_tidy_template = self._clang_templates_dir.joinpath("dot_clang-tidy")
        Utilities.assert_file_existence(
            self._clang_tidy_template, f"Template '{self._clang_tidy_template.resolve()}' is required"
        )

        # Check existance of deps templates
        # ---------------------------------
        deps_templates_dir = self._resources_dir.joinpath("deps")
        Utilities.assert_dir_existence(deps_templates_dir, f"Path '{deps_templates_dir.resolve()}' is required")

        self._repo_dependencies_template = deps_templates_dir.joinpath("deps.repos")
        Utilities.assert_file_existence(
            self._repo_dependencies_template, f"Template '{self._repo_dependencies_template.resolve()}' is required"
        )

        self._custom_install_template = deps_templates_dir.joinpath("install_deps.sh")
        Utilities.assert_file_existence(
            self._custom_install_template, f"Template '{self._custom_install_template.resolve()}' is required"
        )

    def _create(self) -> None:
        use_non_root_img_user = self._img_user != "root"

        # Create directories and files in the project directory.
        # ======================================================

        # Configure catkin tools for ros1.
        if self._ros_variant.get_version() == 1:
            catkin_profiles_dir = self._project_dir.joinpath(".catkin_tools", "profiles", "default")
            Utilities.mkdir(catkin_profiles_dir, 0o755, self._logger.info)

            catkin_config = catkin_profiles_dir.joinpath("config.yaml")
            Utilities.copy_file(self._catkin_config_template, catkin_config, 0o644, self._logger.info)

        # Create Git files.
        gitignore_file = self._project_dir.joinpath(".gitignore")
        Utilities.copy_file(self._gitignore_template, gitignore_file, 0o644, self._logger.info)

        gitlab_dir = self._project_dir.joinpath(".gitlab")
        Utilities.copy_dir(self._gitlab_templates_src_dir, gitlab_dir, 0o755, self._logger.info)

        # Create dependency files.
        repo_file = self._project_dir.joinpath("deps.repos")
        Utilities.copy_file(self._repo_dependencies_template, repo_file, 0o644, self._logger.info)

        install_deps_script = self._project_dir.joinpath("install_deps.sh")
        Utilities.copy_file(self._custom_install_template, install_deps_script, 0o755, self._logger.info)

        # Create README file.
        readme = self._project_dir.joinpath("README.md")
        self._logger.info(f"Creating file '{readme.resolve()}'...")
        Utilities.write_file(f"# Project {self._project_id}\n", readme)

        # Create directories and files under the Docker directory.
        # ========================================================
        docker_dir = self._project_dir.joinpath("docker")
        Utilities.mkdir(docker_dir, 0o755, self._logger.info)

        docker_resources_dir = docker_dir.joinpath(".resources")
        Utilities.mkdir(docker_resources_dir, 0o755, self._logger.info)

        # trim_block removes the first newline after a block (e.g., after {% endif %}).
        # lstrip_blocks strips leading whitespace from the start of a block line.
        jinja2_docker_env = Environment(
            loader=FileSystemLoader(self._docker_templates_dir), trim_blocks=True, lstrip_blocks=True
        )

        jinja2_ros_env = Environment(
            loader=FileSystemLoader(self._ros_templates_dir), trim_blocks=True, lstrip_blocks=True
        )

        deduplicate_path_script = docker_resources_dir.joinpath("deduplicate_path.sh")
        Utilities.copy_file(self._deduplicate_path_template, deduplicate_path_script, 0o755, self._logger.info)

        dot_bash_script = docker_resources_dir.joinpath("dot_bash_aliases")
        Utilities.copy_file(self._dot_bash_aliases_template, dot_bash_script, 0o755, self._logger.info)

        install_core_script = docker_resources_dir.joinpath("install_core.sh")
        Utilities.copy_file(self._install_core_template, install_core_script, 0o755, self._logger.info)

        install_mesa_packages_script = docker_resources_dir.joinpath("install_mesa_packages.sh")
        Utilities.copy_file(
            self._install_mesa_packages_template, install_mesa_packages_script, 0o755, self._logger.info
        )

        install_ros_script = docker_resources_dir.joinpath("install_ros.sh")
        ros_packages = Utilities.read_file(self._ros_packages_template)
        context = {"ros_packages": ros_packages}
        Utilities.install_template(
            jinja2_ros_env, self._install_ros_template, context, install_ros_script, 0o755, self._logger.info
        )

        environment_script = docker_dir.joinpath("environment.sh")
        context = {"ros_distro": self._ros_variant.get_distro()}
        Utilities.install_template(
            jinja2_ros_env, self._environment_template, context, environment_script, 0o755, self._logger.info
        )

        if self._root_environment_template:
            root_environment_script = docker_dir.joinpath("environment_root.sh")
            Utilities.copy_file(self._root_environment_template, root_environment_script, 0o755, self._logger.info)

        rosdep_init_update_script = docker_resources_dir.joinpath("rosdep_init_update.sh")
        Utilities.copy_file(self._rosdep_init_update_template, rosdep_init_update_script, 0o755, self._logger.info)

        if self._rosdep_ignored_key_template:
            rosdep_ignored_key_file = docker_resources_dir.joinpath("rosdep_ignored_keys.yaml")
            Utilities.copy_file(self._rosdep_ignored_key_template, rosdep_ignored_key_file, 0o644, self._logger.info)

        if self._colcon_mixin_metadata_template:
            colcon_mixin_metadata_script = docker_resources_dir.joinpath("colcon_mixin_metadata.sh")
            Utilities.copy_file(
                self._colcon_mixin_metadata_template, colcon_mixin_metadata_script, 0o755, self._logger.info
            )

        rosbuild_script = docker_resources_dir.joinpath("rosbuild.sh")
        Utilities.copy_file(self._rosbuild_template, rosbuild_script, 0o755, self._logger.info)

        dockerignore_file = docker_dir.joinpath("dockerignore")
        Utilities.copy_file(self._dockerignore_template, dockerignore_file, 0o644, self._logger.info)

        # Create build_img.py script.
        build_img_script = docker_dir.joinpath("build_img.py")
        # The project folder is the context for the Docker build.
        # Compute the relative path from the build_img.py script to the project folder.
        # This relative path is used in the build_img script to set the context for the Docker build to the project
        # folder.
        relpath = os.path.relpath(str(self._project_dir.resolve()), str(build_img_script.resolve()))
        context = {
            "supported_docker_platforms": self._supported_docker_platforms,
            "description": f"Builds the Docker image for the project '{self._project_id}', with default id '{self._img_id}', using the default base image '{self._base_img}', for a default platform '{self._docker_platform}', with default active user '{self._img_user}' and the fixed ROS{self._ros_variant.get_version()} distro '{self._ros_variant.get_distro()}'",
            "base_img": self._base_img,
            "docker_platform": self._docker_platform,
            "img_user": self._img_user,
            "img_id": self._img_id,
            "docker_dir": "Path(__file__).parent",
            "context_dir": f'Path(__file__).joinpath("{relpath}").resolve()  # context is the project folder',
            "ros_distro": self._ros_variant.get_distro(),
            "ros_version": self._ros_variant.get_version(),
            "project_id": self._project_id,
        }
        Utilities.install_template(jinja2_docker_env, self._build_img_template, context, build_img_script, 0o755)

        # Create docker-compose file.
        # This is the docker-compose file that will be used to run the container in the robot.
        docker_compose_file = docker_dir.joinpath("docker-compose.yaml")
        context = {
            "service": "appcont",
            "img_id": self._img_id,
            "workspace_dir": f"~/workspaces/{self._project_id}",
            "img_workspace_dir": str(self._img_workspace_dir.resolve()),
            "img_datasets_dir": str(self._img_datasets_dir.resolve()),
            "img_ssh_dir": str(self._img_ssh_dir.resolve()),
            "use_git": False,
            "ext_uid": "1000",
            "ext_upgid": "1000",
        }

        Utilities.install_template(
            jinja2_docker_env, self._docker_compose_template, context, docker_compose_file, 0o644
        )

        # Create entrypoint.sh script.
        entrypoint_script = docker_dir.joinpath("entrypoint.sh")
        Utilities.copy_file(self._entrypoint_template, entrypoint_script, 0o755, self._logger.info)

        # Create Dockerfile.
        dockerfile = docker_dir.joinpath("Dockerfile")
        Utilities.copy_file(self._dockerfile_template, dockerfile, 0o644, self._logger.info)

        # Create src directory structure.
        project_src_dir = self._project_dir.joinpath("src")
        Utilities.mkdir(project_src_dir, 0o755, self._logger.info)

        dependency_dir = project_src_dir.joinpath("0_deps")
        Utilities.mkdir(dependency_dir, 0o755, self._logger.info)

        bringup_pkg_path = project_src_dir.joinpath("bringup")
        Utilities.mkdir(bringup_pkg_path, 0o755, self._logger.info)

        simulation_pkg_path = project_src_dir.joinpath("simulation")
        Utilities.mkdir(simulation_pkg_path, 0o755, self._logger.info)

        # Create clang files.
        clang_format_file = project_src_dir.joinpath(".clang-format")
        Utilities.copy_file(self._clang_format_template, clang_format_file, 0o644, self._logger.info)

        clang_tidy_file = project_src_dir.joinpath(".clang-tidy")
        Utilities.copy_file(self._clang_tidy_template, clang_tidy_file, 0o644, self._logger.info)

        # Create directories in bringup and simulation directory structures.
        folders = ["config", "include", "launch", "rviz", "scripts", "src", "test"]

        for folder in folders:
            path = bringup_pkg_path.joinpath(folder)
            Utilities.mkdir(path, 0o755, self._logger.info)

            path = simulation_pkg_path.joinpath(folder)
            Utilities.mkdir(path, 0o755, self._logger.info)

        bringup_cmakelists_file = bringup_pkg_path.joinpath("CMakeLists.txt")
        Utilities.install_template(
            jinja2_ros_env,
            self._bringup_cmakelists_template,
            {"c_version": self._ros_variant.get_c_version(), "cpp_version": self._ros_variant.get_cpp_version()},
            bringup_cmakelists_file,
            0o755,
        )

        bringup_package_file = bringup_pkg_path.joinpath("package.xml")
        Utilities.copy_file(self._bringup_package_template, bringup_package_file, 0o644, self._logger.info)

        simulation_cmakelists_file = simulation_pkg_path.joinpath("CMakeLists.txt")
        Utilities.install_template(
            jinja2_ros_env,
            self._simulation_cmakelists_template,
            {"c_version": self._ros_variant.get_c_version(), "cpp_version": self._ros_variant.get_cpp_version()},
            simulation_cmakelists_file,
            0o755,
        )

        simulation_package_file = simulation_pkg_path.joinpath("package.xml")
        Utilities.copy_file(self._simulation_package_template, simulation_package_file, 0o644, self._logger.info)

    def _initializate_git_repo(self) -> str:
        cmd = ["git", "init", "--initial-branch=main"]
        cwd = self._project_dir
        self._logger.info(f"Executing command '{' '.join(cmd)}' in '{cwd}'...")
        result = subprocess.run(
            cmd,
            cwd=str(cwd),  # Convert Path to string
            stdout=subprocess.PIPE,  # Capture standard output to prevent automatic printing to the console
            stderr=subprocess.PIPE,  # Capture standard error output to handle errors programmatically
            text=True,  # Convert output from bytes to a string for easier processing
            check=True,  # Raise a CalledProcessError exception if the command fails (non-zero exit code)
        )

        return result.stdout.strip()  # Return the output of the command, removing any leading/trailing whitespace

    def _install_pre_commit_config(self) -> str:
        pre_commit_config = self._project_dir.joinpath(".pre-commit-config.yaml")
        Utilities.copy_file(self._pre_commit_template, pre_commit_config, 0o644, self._logger.info)

        cmd = ["pre-commit", "install"]
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

    # ==========================================================================
    # non-static public methods
    # ==========================================================================

    def create(self) -> None:
        try:
            self._logger.info(f"Creating project '{self._project_id}'...")

            Utilities.mkdir(self._project_dir, 0o755, self._logger.info)

            # Create vscode project if requested.
            if self._vscode_project_creator:
                self._vscode_project_creator.create()

            self._create()
            self._logger.info(self._initializate_git_repo())

            if self._pre_commit_template:
                self._logger.info(self._install_pre_commit_config())
        except RosProjectCreatorException as e:
            self._logger.error(f"{e}")
            raise
