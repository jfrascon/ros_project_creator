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
                project_dir = Path()

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

            resources_dir = Path(__file__).parent.joinpath("resources")
            Utilities.assert_dir_existence(resources_dir, f"Path '{resources_dir.resolve()}' is required")

            ros_variant_yaml_file = resources_dir.joinpath("ros", "ros_variants.yaml")
            ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)

            base_img = Utilities.clean_str(base_img)
            Utilities.assert_non_empty(base_img, "Base image must be a non-empty string")

            if not Utilities.is_valid_docker_image_name(base_img):
                raise RosProjectCreatorException(
                    f"Base image '{base_img}' is not a valid Docker image name. "
                    "Valid names must start with a lowercase letter or number, "
                    "followed by lowercase letters, numbers, underscores, or dashes."
                )

            # If img_is is not provided, it is set to the default value.
            img_id = Utilities.clean_str(img_id) or f"{self._project_id}:latest"

            if not Utilities.is_valid_docker_image_name(img_id):
                raise RosProjectCreatorException(
                    f"Image ID '{img_id}' is not a valid Docker image name. "
                    "Valid names must start with a lowercase letter or number, "
                    "followed by lowercase letters, numbers, underscores, or dashes."
                )

            img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(img_user, "Image user must be a non-empty string")

            if " " in img_user:
                raise RosProjectCreatorException("Image user must not contain spaces")

            if img_user == "root":
                img_user_home = Path(f"/{img_user}")
            else:
                img_user_home = Path(f"/home/{img_user}")

            img_workspace_dir = img_user_home.joinpath("workspace")
            img_datasets_dir = img_user_home.joinpath("datasets")
            img_ssh_dir = img_user_home.joinpath(".ssh")

            relative_build_script = Path("docker/build.py")
            build_script = self._project_dir.joinpath(relative_build_script)
            relpath = os.path.relpath(str(self._project_dir), str(build_script))

            ros_packages_file = resources_dir.joinpath(f"ros/packages_ros{ros_variant.get_version()}.txt")
            Utilities.assert_file_existence(ros_packages_file, f"File '{ros_packages_file}' is required")
            ros_packages = Utilities.read_file(ros_packages_file)

            relative_brigup_pkg_path = Path("src/bringup")
            relative_simulation_pkg_path = Path("src/simulation")

            # By using a dictionary we can sort the keys and create the files in a specific order, because the key
            # is the file to create, relative to the project directory.
            # The value is a tuple with the source file path, the context for Jinja2 rendering (if any), and the file
            # permissions.
            # The source file path is relative to the resources directory.
            # The context is a dictionary with the variables to be replaced in the Jinja2 template.
            # The file permissions are the octal permissions to be set for the file.
            items_to_process = {
                ".gitignore": ("git/dot_gitignore", None, 0o664),
                ".gitlab": ("git/gitlab", None, 0o775),
                "deps.repos": ("deps/deps.repos", None, 0o664),
                "docker/.resources/deduplicate_path.sh": ("scripts/deduplicate_path.sh", None, 0o775),
                "docker/.resources/dot_bash_aliases.sh": ("scripts/dot_bash_aliases", None, 0o775),
                "docker/.resources/install_base_system.sh": (
                    "scripts/install_base_system.sh",
                    None,
                    0o775,
                ),
                "docker/.resources/install_ros.sh": ("ros/install_ros.j2", {"ros_packages": ros_packages}, 0o775),
                "docker/.resources/rosbuild.sh": (f"ros/ros{ros_variant.get_version()}build.sh", None, 0o775),
                "docker/.resources/rosdep_init_update.sh": ("ros/rosdep_init_update.sh", None, 0o775),
                "docker/build.py": (
                    "docker/build.j2",
                    {
                        "description": f"Builds the Docker image '{img_id}' for the project '{self._project_id}', using the base image '{base_img}', with active user '{img_user}' and 'ROS{ros_variant.get_version()}-{ros_variant.get_distro()}'",
                        "base_img": base_img,
                        "img_user": img_user,
                        "img_id": img_id,
                        "docker_dir": "Path(__file__).parent",
                        "context_dir": f'Path(__file__).joinpath("{relpath}").resolve()  # context is the project folder',
                        "ros_distro": ros_variant.get_distro(),
                        "ros_version": ros_variant.get_version(),
                        "project_id": self._project_id,
                    },
                    0o775,
                ),
                "docker/docker-compose.yaml": (
                    "docker/docker-compose.j2",
                    {
                        "service": "appcont",
                        "img_id": img_id,
                        "workspace_dir": f"~/workspaces/{self._project_id}",
                        "img_workspace_dir": str(img_workspace_dir),
                        "img_datasets_dir": str(img_datasets_dir),
                        "img_ssh_dir": str(img_ssh_dir),
                        "use_git": False,
                        "ext_uid": "1000",
                        "ext_upgid": "1000",
                    },
                    0o664,
                ),
                "docker/Dockerfile": ("docker/Dockerfile", None, 0o664),
                "docker/dockerignore": ("docker/dot_dockerignore", None, 0o664),
                "docker/entrypoint.sh": ("docker/entrypoint.sh", None, 0o775),
                "docker/environment.sh": (
                    f"ros/environment_ros{ros_variant.get_version()}.j2",
                    {"ros_distro": ros_variant.get_distro()},
                    0o775,
                ),
                "install_deps.sh": ("deps/install_deps.sh", None, 0o775),
                "src/.clang-format": ("clang/dot_clang-format", None, 0o664),
                "src/.clang-tidy": ("clang/dot_clang-tidy", None, 0o664),
                "src/bringup/CMakeLists.txt": (
                    f"ros/bringup_CMakeLists_ros{ros_variant.get_version()}.j2",
                    {
                        "c_version": ros_variant.get_c_version(),
                        "cpp_version": ros_variant.get_cpp_version(),
                    },
                    0o664,
                ),
                "src/bringup/package.xml": (
                    f"ros/bringup_package_ros{ros_variant.get_version()}.xml",
                    None,
                    0o664,
                ),
                "src/simulation/CMakeLists.txt": (
                    f"ros/simulation_CMakeLists_ros{ros_variant.get_version()}.j2",
                    {
                        "c_version": ros_variant.get_c_version(),
                        "cpp_version": ros_variant.get_cpp_version(),
                    },
                    0o664,
                ),
                "src/simulation/package.xml": (
                    f"ros/simulation_package_ros{ros_variant.get_version()}.xml",
                    None,
                    0o664,
                ),
            }

            if use_pre_commit:
                self._check_pre_commit_binary_existance()

                items_to_process[".pre-commit-config.yaml"] = ("git/dot_pre-commit-config.yaml", None, 0o664)

            if ros_variant.get_version() == 1:
                items_to_process[".catkin_tools/profiles/default/config.yaml"] = (
                    "ros/catkin_config_ros1.yaml",
                    None,
                    0o664,
                )
            else:
                items_to_process["docker/.resources/colcon_mixin_metadata.sh"] = (
                    "ros/colcon_mixin_metadata.sh",
                    None,
                    0o775,
                )
                items_to_process["docker/.resources/rosdep_ignored_keys.yaml"] = (
                    "ros/rosdep_ignored_keys_ros2.yaml",
                    None,
                    0o664,
                )

            self._check_git_binary_existance()

            self._logger.info(f"Creating project '{self._project_id}'")

            for key in sorted(items_to_process.keys()):
                item = items_to_process[key]

                dst_item = self._project_dir.joinpath(key).resolve()
                src_item = resources_dir.joinpath(item[0]).resolve()

                if not src_item.exists():
                    raise RosProjectCreatorException(
                        f"Required resource '{src_item.resolve()}' does not exist. "
                        "Please check the resources directory."
                    )

                if src_item.is_dir():
                    # If the source item is a directory, copy the directory recursively.
                    self._logger.info(f"Creating directory '{dst_item}'")
                    shutil.copytree(src_item, dst_item, copy_function=shutil.copy2)
                else:
                    # If the source item is a file, copy the file.
                    self._logger.info(f"Creating file '{dst_item.resolve()}'")

                    if not dst_item.parent.exists():
                        dst_item.parent.mkdir(parents=True, mode=0o775)

                    if item[1] is not None:
                        jinja2_env = Environment(
                            loader=FileSystemLoader(src_item.parent), trim_blocks=True, lstrip_blocks=True
                        )
                        jinja2_template = jinja2_env.get_template(src_item.name)
                        rendered_text = jinja2_template.render(item[1])

                        with dst_item.open("w") as f:
                            f.write(rendered_text)
                    else:
                        shutil.copy2(src_item, dst_item)

                    dst_item.chmod(item[2])  # Set the file permissions

            # Create directories in bringup and simulation directory structures.
            folders = ["config", "launch", "rviz", "scripts"]

            for folder in folders:
                path = self._project_dir.joinpath(relative_brigup_pkg_path, folder)
                self._logger.info(f"Creating directory '{path}'")
                path.mkdir(parents=True, mode=0o775)

                path = self._project_dir.joinpath(relative_simulation_pkg_path, folder)
                self._logger.info(f"Creating directory '{path}'")
                path.mkdir(parents=True, mode=0o775)

            # Create README file.
            readme = self._project_dir.joinpath("README.md")
            self._logger.info(f"Creating file '{readme}'")
            Utilities.write_file(f"# Project {self._project_id}\n", readme)

            # Create VSCode project if requested.
            if use_vscode_project:
                self._vscode_project_creator = VscodeProjectCreator(
                    ros_variant.get_distro(),
                    img_id,
                    img_user,
                    self._project_dir,
                    img_workspace_dir,
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
