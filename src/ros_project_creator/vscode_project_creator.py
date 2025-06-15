#!/usr/bin/env python3

import shutil
from pathlib import Path
import os

from jinja2 import Environment, FileSystemLoader

from ros_project_creator.colorizedlogs import ColorizedLogger

from ros_project_creator.ros_variant import RosVariant
from ros_project_creator.utilities import Utilities


class VscodeProjectCreatorException(Exception):
    """Base exception for all errors related to VscodeProjectCreator."""

    pass


class VscodeProjectCreator:

    # ==========================================================================
    # non-static private methods
    # ==========================================================================

    def __init__(
        self,
        ros_distro: str,
        img_id: str,
        img_user: str,
        img_user_home: Path,
        workspace_dir: Path,
        img_workspace_dir: Path,
        use_host_nvidia_driver: bool = False,
        use_console_log: bool = True,
        log_file: str = "",
        log_level: str = "DEBUG",
    ):
        """Creates a new VSCode project based on templates.
        Args:
            ros_distro (str): ROS distro to use (e.g. 'humble')
            img_id (str): ID of the Docker image that VSCode will use to create a container
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

        # The constructor may raise an Exception. It is not wrapped in a try-except block
        # because the exception handler logs the error. However, if the logger's construction
        # fails, logging statements cannot be executed.
        self._logger = ColorizedLogger(
            name="VscodeProjectCreator", use_console_log=use_console_log, log_file=log_file, log_level=log_level
        )
        try:
            # Check the resource dir exits.
            self._resources_dir = Path(__file__).parent.joinpath("resources")
            Utilities.assert_dir_existence(self._resources_dir, f"Path '{str(self._resources_dir)}' is required")

            # Get the the ros_variant (ros_distro, ros_version, cpp_version, c_version) associated to the passed
            # ros_distro.
            ros_variant_yaml_file = self._resources_dir.joinpath("ros/ros_variants.yaml")
            self._ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)

            self._img_id = Utilities.clean_str(img_id)
            Utilities.assert_non_empty(img_id, "Image id must be a non-empty string")

            self._img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(img_user, "Image user must be a non-empty string")

            # The paths on the image side, in the docker-compose file, must be absolute paths.
            # The img_datasets_dir and the img_ssh_dir will be created from the img_user_home path,
            # so we need the img_user_home to be an absolute path.
            if not img_user_home:
                raise Exception("Image user home path must be provided")

            if not img_user_home.is_absolute():
                raise Exception("Image user home path must be an absolute path")

            self._img_user_home = img_user_home

            self._img_datasets_dir = self._img_user_home.joinpath("datasets")
            self._img_ssh_dir = self._img_user_home.joinpath(".ssh")

            # The workspace_dir field can't be None. It does not matter if it is an absolute or
            # relative path, i.e., as long as the user provides a path. It is the responsibility
            # of the user to provide the path, where the vscode files will be created.
            # If the workspace directory does not exist, it does not matter, it will be creater
            # later.
            if not workspace_dir:
                raise Exception("Image workspace path must be provided")

            self._workspace_dir = workspace_dir.expanduser().resolve()

            if not img_workspace_dir:
                raise Exception("Image workspace path must be provided")

            if not img_workspace_dir.is_absolute():
                raise Exception("Image workspace path must be an absolute path")

            self._img_workspace_dir = img_workspace_dir
            self._use_host_nvidia_driver = use_host_nvidia_driver

            # Get git config for the user running the project configuration tool and write it to the docker-compose
            # file, in the volumes section.
            home = Path.home()
            global_gitconfig_file = home.joinpath(".gitconfig")
            xdg_gitconfig_file = home.joinpath(".config/git/config")

            # Check ~/.gitconfig first, as it has higher priority.
            if global_gitconfig_file.is_file():
                self._use_git = True
                self._gitconfig_file = global_gitconfig_file
            # If not found, check ~/.config/git/config (lower priority)
            elif xdg_gitconfig_file.is_file():
                self._use_git = True
                self._gitconfig_file = xdg_gitconfig_file
            # If no gitconfig file is found, remove the git_config block from the docker-compose file.
            else:
                self._use_git = False
                self._gitconfig_file = None

            if self._ros_variant.get_version() == "1":
                self._build_release_cmd = "rosbuild.sh"
                self._build_debug_cmd = "rosbuild.sh --cmake-args -DCMAKE_BUILD_TYPE=Debug"
                self._build_relwithdebinfo_cmd = "rosbuild.sh --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo"
                self._clean_cmd = "catkin clean --yes --verbose --force"
            else:
                self._build_release_cmd = "rosbuild.sh"
                self._build_debug_cmd = "rosbuild.sh --mixin debug"
                self._build_relwithdebinfo_cmd = "rosbuild.sh --mixin rel-with-deb-info"
                self._clean_cmd = "colcon clean workspace -y"

            self._install_items()
        # trim_block removes the first newline after a block (e.g., after {% endif %}).
        # lstrip_blocks strips leading whitespace from the start of a block line.
        except Exception as e:
            self._logger.error(f"{e}")
            raise

    def _create_items_to_install(self) -> None:
        service = "devcont"

        self._items_to_install = {
            ".devcontainer/devcontainer.json": [
                "vscode/dot_devcontainer.j2",
                {"service": service, "img_user": self._img_user, "img_workspace_dir": self._img_workspace_dir},
                False,
            ],
            ".devcontainer/docker-compose.yaml": [
                "docker/docker-compose.j2",
                {
                    "service": service,
                    "img_id": self._img_id,
                    "use_host_nvidia_driver": self._use_host_nvidia_driver,
                    "workspace_dir": self._workspace_dir,
                    "img_workspace_dir": self._img_workspace_dir,
                    "img_datasets_dir": self._img_datasets_dir,
                    "img_ssh_dir": self._img_ssh_dir,
                    "use_git": self._use_git,
                    "gitconfig_file": self._gitconfig_file,
                    "img_gitconfig_file": self._img_user_home.joinpath(".gitconfig"),
                    "ext_uid": f"{os.getuid()}",
                    "ext_upgid": f"{os.getgid()}",
                },
                True,
            ],
            ".vscode/c_cpp_properties.json": [
                "vscode/c_cpp_properties.j2",
                {
                    "c_version": f"c{self._ros_variant.get_c_version()}",
                    "cpp_version": f"c++{self._ros_variant.get_cpp_version()}",
                    "ros_distro": self._ros_variant.get_distro(),
                },
                False,
            ],
            ".vscode/settings.json": ["vscode/settings.json", True],
            ".vscode/tasks.json": [
                "vscode/tasks.j2",
                {
                    "build_command_for_release": self._build_release_cmd,
                    "build_command_for_debug": self._build_debug_cmd,
                    "build_command_for_relwithdebinfo": self._build_relwithdebinfo_cmd,
                    "clean_command": self._clean_cmd,
                },
                True,
            ],
            "ws.code-workspace": ["vscode/ws.j2", {"ros_distro": self._ros_variant.get_distro()}, False],
        }

    def _install_items(self) -> None:
        self._create_items_to_install()

        for key in sorted(self._items_to_install.keys()):
            dst_path = self._workspace_dir.joinpath(key)

            item = self._items_to_install[key]

            # If the item[0] is None, it means that the key, that can be a file or a directory, must
            # be created, not copied from a resource.
            src_path = None
            resource_path_str = item[0]

            if resource_path_str is not None:
                if resource_path_str.startswith("/"):
                    src_path = Path(resource_path_str)
                else:
                    src_path = self._resources_dir.joinpath(resource_path_str)

                if not src_path.exists():
                    raise VscodeProjectCreatorException(f"Required resource '{str(src_path)}' does not exist.")

            # Remove the dst_path if it exists, to ensure a clean copy/creation.
            if dst_path.is_file():
                dst_path.unlink()
            elif dst_path.is_dir():
                dst_path.rmdir()

            # len = 1 -> directory
            #    src_path is None -> create an empty directory
            #    src_path is not None -> copy the directory recursively
            # len = 2 -> file with permissions
            #    src_path is None -> create an empty file with permissions
            #    src_path is not None -> copy the file with permissions
            # len = 3 -> file with Jinja2 rendering and permissions
            #    src_path is None -> raise an exception, not allowed
            #    src_path is not None -> copy the file with Jinja2 rendering and permissions
            if len(item) == 1:
                self._logger.info(f"Creating directory '{str(dst_path)}'")

                if src_path is not None:
                    if not src_path.is_dir():
                        raise VscodeProjectCreatorException(f"Directory '{str(src_path)}' is required")

                    # Create the parent directory if it does not exist.
                    if not dst_path.parent.exists():
                        dst_path.parent.mkdir(parents=True)

                    shutil.copytree(src_path, dst_path, copy_function=shutil.copy2)
                    dst_path.chmod(0o775)
                else:
                    # When src_path is None, the key is a directory that must be created.
                    dst_path.mkdir(parents=True)
            elif len(item) == 2:
                self._logger.info(f"Creating file '{str(dst_path)}'")

                if src_path is not None:
                    if not src_path.is_file():
                        raise VscodeProjectCreatorException(f"File '{str(src_path)}' is required.")

                    # Create the parent directory if it does not exist.
                    if not dst_path.parent.exists():
                        dst_path.parent.mkdir(parents=True)

                    shutil.copy2(src_path, dst_path)
                else:
                    # When src_path is None, the key is a file that must be created.
                    dst_path.touch()

                if item[1]:
                    dst_path.chmod(0o775)
                else:
                    dst_path.chmod(0o664)
            elif len(item) == 3:
                self._logger.info(f"Creating file '{dst_path}'")

                if src_path is None:
                    raise VscodeProjectCreatorException(
                        f"Relative source path can't be empty for element '{str(dst_path)}'."
                    )

                if not src_path.is_file():
                    raise VscodeProjectCreatorException(f"Template '{str(src_path)}' is required.")

                context = item[1]

                if context is None:
                    raise VscodeProjectCreatorException(
                        f"Context for Jinja2 rendering can't be None for element '{str(dst_path)}'."
                    )

                if not isinstance(context, dict):
                    raise VscodeProjectCreatorException(
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
