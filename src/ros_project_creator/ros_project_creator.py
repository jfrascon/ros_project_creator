#!/usr/bin/env python3

import os
from pathlib import Path
import pwd
import shutil
import subprocess
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from ros_project_creator.colorizedlogs import ColorizedLogger

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
        img_user: Optional[str],
        img_id: Optional[str],
        custom_entrypoint: Optional[Path],
        use_base_img_entrypoint=False,
        custom_environment: Optional[Path] = None,
        use_environment: bool = True,
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

            project_dir_str = str(project_dir).strip()

            # If the project_dir contains only whitespace, then the project_dir is set to the
            # current working directory (Path()).
            if project_dir_str == "":
                self._project_dir = Path()
            else:
                # Remove leading and trailing whitespace, so paths like
                # "   /home/user/project"    => "/home/user/project" or
                # "/home/user/project   "    => "/home/user/project" or
                # "   /home/user/project   " => "/home/user/project"
                # are accepted.
                self._project_dir = Path(project_dir_str).expanduser().resolve()

            # Get home of the user who actually invoked the script (even under sudo)
            # When running under sudo, the environment variable SUDO_USER is set to the user who invoked sudo.
            real_user = os.getenv("SUDO_USER") or os.getenv("USER")

            if not real_user:
                raise RosProjectCreatorException("Unable to determine the active user")

            user_home = Path(pwd.getpwnam(real_user).pw_dir).resolve()

            # Ensure project_dir is inside the user's home.
            try:
                self._project_dir.relative_to(user_home)
            except ValueError:
                raise RosProjectCreatorException(
                    f"Error: Project directory is '{str(self._project_dir)}'. Project directory must be inside the home of the active user '{user_home}'"
                )

            # If the project dir already exist, do nothing, print message and exit.
            # The user must decide how to proceed manually (deleting the existing project dir and re-create the project,
            # create the project in a differente directory, etc.)
            # etc.)
            if self._project_dir.exists():
                raise RosProjectCreatorException(
                    f"Project dir '{str(self._project_dir)}' already exists. "
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

            self._img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(self._img_user, "Image user must be a non-empty string")

            if " " in self._img_user:
                raise RosProjectCreatorException("Image user must not contain spaces")

            if self._img_user == "root":
                self._img_user_home = Path(f"/{self._img_user}")
            else:
                self._img_user_home = Path(f"/home/{self._img_user}")

            self._img_workspace_dir = self._img_user_home.joinpath("workspace")
            self._img_datasets_dir = self._img_user_home.joinpath("datasets")
            self._img_ssh_dir = self._img_user_home.joinpath(".ssh")

            # If img_id is not provided, it is set to the default value.
            self._img_id = Utilities.clean_str(img_id) or f"{self._project_id}:latest"

            if not Utilities.is_valid_docker_image_name(self._img_id):
                raise RosProjectCreatorException(
                    f"Image ID '{self._img_id}' is not a valid Docker image name. "
                    "Valid names must start with a lowercase letter or number, "
                    "followed by lowercase letters, numbers, underscores, or dashes."
                )

            self._custom_entrypoint = custom_entrypoint
            self._use_base_img_entrypoint = use_base_img_entrypoint
            self._use_environment = use_environment
            self._custom_environment = custom_environment

            if self._custom_entrypoint is not None and self._use_base_img_entrypoint:
                raise RosProjectCreatorException(
                    "custom_entrypoint and use_base_img_entrypoint are mutually exclusive arguments."
                )

            # Check if the git binary exists in the system.
            self._check_git_binary_existance()

            # If the pre-commit argument is True, check if the pre-commit binary exists in the
            # system.
            self._use_pre_commit = use_pre_commit

            if self._use_pre_commit:
                self._check_pre_commit_binary_existance()

            self._logger.info(f"Creating project '{self._project_id}'")

            self._install_items()

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

            self._logger.info(self._initializate_git_repo())

            if use_pre_commit:
                self._logger.info(self._install_pre_commit_config())
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

    def _create_items_to_install(self) -> None:
        docker_dir = self._project_dir.joinpath("docker")

        # Relative path to the build script from the project directory.
        relative_build_script = Path("docker/build.py")
        # Path to the build script.
        build_script = self._project_dir.joinpath(relative_build_script)

        # Relative path to the deps file from the project directory.
        relative_deps_file = Path("deps.repos")
        # Path to the deps file.
        deps_file = self._project_dir.joinpath(relative_deps_file)

        # Path where the dependency packages will be installed.
        relative_deps_targer_dir = Path("src/0_deps")
        deps_target_dir = self._project_dir.joinpath(relative_deps_targer_dir)

        # The context directory is the project directory.
        relpath_to_context_dir_from_build_script = os.path.relpath(str(self._project_dir), str(build_script))
        relpath_to_docker_dir_from_build_script = os.path.relpath(str(docker_dir), str(build_script))
        relpath_to_deps_file_from_build_script = os.path.relpath(str(deps_file), str(build_script))
        relpath_to_deps_target_dir_from_build_script = os.path.relpath(str(deps_target_dir), str(build_script))

        ros_packages_file = self._resources_dir.joinpath(f"ros/packages_ros{self._ros_variant.get_version()}.txt")
        Utilities.assert_file_existence(ros_packages_file, f"File '{ros_packages_file}' is required")
        ros_packages = Utilities.read_file(ros_packages_file)

        if not ros_packages.strip():
            raise RosProjectCreatorException(f"File 'packages_ros{ros_version}.txt' is empty.")

        ros_env_vars_file = self._resources_dir.joinpath(
            f"ros/environment_variables_ros{self._ros_variant.get_version()}.txt"
        )
        Utilities.assert_file_existence(ros_env_vars_file, f"File '{ros_env_vars_file}' is required")
        ros_env_vars = Utilities.read_file(ros_env_vars_file)

        if not ros_env_vars.strip():
            raise RosProjectCreatorException(
                f"File 'environment_variables_ros{self._ros_variant.get_version()}.txt' is empty."
            )

        # By using a dictionary we can sort the keys and create the files in a specific order,
        # because the key is the file to create, relative to the project directory.

        # The value is a list:
        # If the list has one element, the key represents a directory to be 'created' somehow.
        #    If the first element of the list is not None, then this element is a directory to be
        #    copied in the path specified by the key.
        #    If the first element of the list is None, then the key is a directory to be created.
        #
        # If the list has two elements, the key represents a file to be 'created' somehow.
        #    If the first element of the list is not None, then this element is a file to be
        #    copied in the path specified by the key. The second element of the list is a boolean
        #    indicating if the file should be created with executable permissions (T) or not (F).
        #    If the first element of the list is None, then the key is a file to be created, and the
        #    second element of the list is a boolean indicating if the file should be created with
        #    executable permissions (T) or not (F).
        #
        # If the list has three elements, the key represents a file to be 'created' with Jinja2
        # rendering. The first element of the list is the source file path, which is a Jinja2
        # template. The second element is a dictionary with the context for Jinja2 rendering.
        # The third element is a boolean indicating if the file should be created with executable
        # permissions (True) or not (False).

        #  with the source file path, the context for Jinja2 rendering (if any), and the file
        # permissions.
        # The source file path is relative to the resources directory.
        # The context is a dictionary with the variables to be replaced in the Jinja2 template.
        # The third element is a boolean indicating if the file should be created with executable
        # permissions (True) or not (False).

        self._items_to_install = {
            ".gitignore": ["git/dot_gitignore", False],
            ".gitlab": ["git/gitlab"],
            f"{str(relative_deps_file)}": ["deps/deps.repos", False],
            "docker/.resources/deduplicate_path.sh": ["scripts/deduplicate_path.sh", True],
            "docker/.resources/dot_bash_aliases.sh": ["scripts/dot_bash_aliases", True],
            "docker/.resources/install_base_system.sh": ["scripts/install_base_system.sh", True],
            "docker/.resources/install_ros.sh": [
                "ros/install_ros.j2",
                {"use_environment": self._use_environment, "ros_packages": ros_packages},
                True,
            ],
            "docker/.resources/rosbuild.sh": [f"ros/ros{self._ros_variant.get_version()}build.sh", True],
            "docker/.resources/rosdep_init_update.sh": ["ros/rosdep_init_update.sh", True],
            "docker/Dockerfile": [
                "docker/Dockerfile.j2",
                {
                    "ros_distro": self._ros_variant.get_distro(),
                    "ros_version": self._ros_variant.get_version(),
                    "use_base_img_entrypoint": self._use_base_img_entrypoint,
                    "use_environment": self._use_environment,
                    "extra_ros_env_vars": ros_env_vars,
                },
                False,
            ],
            str(relative_build_script): [
                "docker/build.j2",
                {
                    "description": f"Builds the Docker image '{self._img_id}' for the project '{self._project_id}', using the base image '{self._base_img}', with active user '{self._img_user}' and 'ROS{self._ros_variant.get_version()}-{self._ros_variant.get_distro()}'",
                    "project_id": self._project_id,
                    "relpath_to_docker_dir": relpath_to_docker_dir_from_build_script,
                    "relpath_to_context_dir": relpath_to_context_dir_from_build_script,
                    "base_img": self._base_img,
                    "img_id": self._img_id,
                    "img_user": self._img_user,
                    "img_user_home": str(self._img_user_home),
                    "ros_distro": self._ros_variant.get_distro(),
                    "ros_version": self._ros_variant.get_version(),
                    "deps_file": relpath_to_deps_file_from_build_script,
                    "deps_target_dir": relpath_to_deps_target_dir_from_build_script,
                },
                True,
            ],
            "docker/docker-compose.yaml": [
                "docker/docker-compose.j2",
                {
                    "service": "appcont",
                    "img_id": self._img_id,
                    "workspace_dir": f"~/workspaces/{self._project_id}",
                    "img_workspace_dir": str(self._img_workspace_dir),
                    "img_datasets_dir": str(self._img_datasets_dir),
                    "img_ssh_dir": str(self._img_ssh_dir),
                    "use_git": False,
                    "ext_uid": "1000",
                    "ext_upgid": "1000",
                },
                False,
            ],
            "docker/dockerignore": ["docker/dot_dockerignore", False],
            "install_deps.sh": ["deps/install_deps.sh", True],
            "README.md": [
                "README.j2",
                {
                    "project_id": self._project_id,
                },
                False,
            ],
            "src/.clang-format": ["clang/dot_clang-format", False],
            "src/.clang-tidy": ["clang/dot_clang-tidy", False],
            str(relative_deps_targer_dir): [None],
            "src/bringup/CMakeLists.txt": [
                f"ros/bringup_CMakeLists_ros{self._ros_variant.get_version()}.j2",
                {
                    "c_version": self._ros_variant.get_c_version(),
                    "cpp_version": self._ros_variant.get_cpp_version(),
                },
                False,
            ],
            "src/bringup/config": [None],
            "src/bringup/launch": [None],
            "src/bringup/package.xml": [
                f"ros/bringup_package_ros{self._ros_variant.get_version()}.xml",
                False,
            ],
            "src/bringup/rviz": [None],
            "src/bringup/scripts": [None],
            "src/simulation/CMakeLists.txt": [
                f"ros/simulation_CMakeLists_ros{self._ros_variant.get_version()}.j2",
                {
                    "c_version": self._ros_variant.get_c_version(),
                    "cpp_version": self._ros_variant.get_cpp_version(),
                },
                False,
            ],
            "src/simulation/config": [None],
            "src/simulation/launch": [None],
            "src/simulation/package.xml": [
                f"ros/simulation_package_ros{self._ros_variant.get_version()}.xml",
                False,
            ],
            "src/simulation/rviz": [None],
            "src/simulation/scripts": [None],
        }

        if self._use_pre_commit:
            self._items_to_install[".pre-commit-config.yaml"] = ["git/dot_pre-commit-config.yaml", False]

        if self._ros_variant.get_version() == 1:
            self._items_to_install[".catkin_tools/profiles/default/config.yaml"] = [
                "ros/catkin_config_ros1.yaml",
                False,
            ]
        else:
            self._items_to_install["docker/.resources/colcon_mixin_metadata.sh"] = [
                "ros/colcon_mixin_metadata.sh",
                True,
            ]
            self._items_to_install["docker/.resources/rosdep_ignored_keys.yaml"] = [
                "ros/rosdep_ignored_keys_ros2.yaml",
                False,
            ]

        if not self._use_base_img_entrypoint:
            if self._custom_entrypoint is not None:
                self._custom_entrypoint = self._custom_entrypoint.expanduser().resolve()

                # if not entrypoint.is_file() or entrypoint.stat().st_size == 0:
                if not self._custom_entrypoint.exists():
                    raise RosProjectCreatorException(
                        f"Custom entrypoint file '{str(self._custom_entrypoint)}' not found"
                    )

                self._items_to_install["docker/entrypoint.sh"] = [str(self._custom_entrypoint), True]
            else:
                self._items_to_install["docker/entrypoint.sh"] = ["docker/entrypoint.sh", True]

        if self._use_environment:
            if self._custom_environment is not None:
                self._custom_environment = self._custom_environment.expanduser().resolve()

                if not self._custom_environment.exists():
                    raise RosProjectCreatorException(
                        f"Custom environment file '{str(self._custom_environment)}' not found"
                    )

                self._items_to_install["docker/.resources/environment.sh"] = [
                    str(self._custom_environment),
                    True,
                ]
            else:
                self._items_to_install["docker/.resources/environment.sh"] = [
                    f"ros/environment_ros{self._ros_variant.get_version()}.j2",
                    {"ros_distro": self._ros_variant.get_distro()},
                    True,
                ]

    def _initializate_git_repo(self) -> str:
        cmd = ["git", "init", "--initial-branch=main"]
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

        for key in sorted(self._items_to_install.keys()):
            dst_path = self._project_dir.joinpath(key).resolve()

            item = self._items_to_install[key]
            relative_src_path = item[0]

            if len(item) == 1:
                self._logger.info(f"Creating directory '{dst_path}'")

                if relative_src_path is not None:
                    src_path = self._resources_dir.joinpath(relative_src_path).resolve()

                    if not src_path.exists():
                        raise RosProjectCreatorException(f"Required resource '{str(src_path)}' does not exist.")

                    if not src_path.is_dir():
                        raise RosProjectCreatorException(f"Required resource '{str(src_path)}' is not a directory.")

                    if not dst_path.parent.exists():
                        dst_path.parent.mkdir(parents=True)

                    shutil.copytree(src_path, dst_path, copy_function=shutil.copy2)
                    dst_path.chmod(0o775)
                else:
                    dst_path.mkdir(parents=True)
            elif len(item) == 2:
                self._logger.info(f"Creating file '{dst_path}'")

                if relative_src_path is not None:
                    src_path = self._resources_dir.joinpath(item[0]).resolve()

                    if not src_path.exists():
                        raise RosProjectCreatorException(f"Required resource '{str(src_path)}' does not exist.")

                    if not src_path.is_file():
                        raise RosProjectCreatorException(f"Required resource '{str(src_path)}' is not a file.")

                    if not dst_path.parent.exists():
                        dst_path.parent.mkdir(parents=True)

                    shutil.copyfile(src_path, dst_path)
                else:
                    dst_path.touch()

                if item[1]:
                    dst_path.chmod(0o775)
                else:
                    dst_path.chmod(0o664)
            elif len(item) == 3:
                self._logger.info(f"Creating file '{dst_path}'")

                if relative_src_path is None:
                    raise RosProjectCreatorException(
                        f"Relative source path can't be empty for element '{str(dst_path)}'."
                    )

                src_path = self._resources_dir.joinpath(item[0]).resolve()

                if not src_path.exists():
                    raise RosProjectCreatorException(f"Required resource '{str(src_path)}' does not exist.")

                if not src_path.is_file():
                    raise RosProjectCreatorException(f"Required resource '{str(src_path)}' is not a file.")

                context = item[1]

                if context is None:
                    raise RosProjectCreatorException(
                        f"Context for Jinja2 rendering can't be None for element '{str(dst_path)}'."
                    )

                if not isinstance(context, dict):
                    raise RosProjectCreatorException(
                        f"Context for Jinja2 rendering must be a dictionary for element '{str(dst_path)}'."
                    )

                if not dst_path.parent.exists():
                    dst_path.parent.mkdir(parents=True)

                jinja2_env = Environment(loader=FileSystemLoader(src_path.parent), trim_blocks=True, lstrip_blocks=True)
                jinja2_template = jinja2_env.get_template(src_path.name)
                rendered_text = jinja2_template.render(context)

                with dst_path.open("w") as f:
                    f.write(rendered_text)

                if item[2]:
                    dst_path.chmod(0o775)
                else:
                    dst_path.chmod(0o664)

    def _install_pre_commit_config(self) -> str:
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
