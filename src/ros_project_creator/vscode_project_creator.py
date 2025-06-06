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
        workspace_dir: Path,
        img_workspace_dir: Path,
        use_console_log: bool = True,
        log_file: str = "",
        log_level: str = "DEBUG",
    ):
        """Creates a new VSCode project based on templates.
        Args:
            ros_distro (str): ROS distro to use (e.g. 'humble')
            img_id (str): ID of the Docker image that VSCode will use to create a container
            img_user (str): User to use inside the container
            workspace_dir (Path): Path to the project directory (e.g. '/path/to/robproj')
            img_workspace_dir (Path): Path to the workspace in the image (e.g. '/home/user/workspaces/robproj')
            use_console_log (bool): If True, log to console. Default is True.
            log_file (str): File to log output. Default is "" (no file).
            log_level (str): Logging level. Default is "DEBUG".
        Raises:
            Exception: If any of the arguments are invalid or if the resources directory does not exist.
        """

        # The constructor may raise an Exception. It is not wrapped in a try-except block
        # because the exception handler logs the error. However, if the logger's construction
        # fails, logging statements cannot be executed.
        self._logger = ColorizedLogger(
            name="VscodeProjectCreator", use_console_log=use_console_log, log_file=log_file, log_level=log_level
        )
        try:
            # Check the resource dir exits.
            resources_dir = Path(__file__).parent.joinpath("resources")
            Utilities.assert_dir_existence(resources_dir, f"Path '{resources_dir.resolve()}' is required")

            # Get the the ros_variant (ros_distro, ros_version, cpp_version, c_version) associated to the passed
            # ros_distro.
            ros_variant_yaml_file = resources_dir.joinpath("ros/ros_variants.yaml")
            ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)

            img_id = Utilities.clean_str(img_id)
            Utilities.assert_non_empty(img_id, "Image id must be a non-empty string")

            img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(img_user, "Image user must be a non-empty string")

            if not workspace_dir:
                raise Exception("Workspace path must be provided")

            # If the workspace directory does not exist, it does not matter, it will be creater later, in the run
            # method.

            if not img_workspace_dir:
                raise Exception("Image workspace path must be provided")

            img_user_home = Path("/root") if img_user == "root" else Path(f"/home/{img_user}")

            # Get git config for the user running the project configuration tool and write it to the docker-compose
            # file, in the volumes section.
            home = Path.home()
            global_gitconfig_file = home.joinpath(".gitconfig")
            xdg_gitconfig_file = home.joinpath(".config/git/config")

            # Check ~/.gitconfig first, as it has higher priority.
            if global_gitconfig_file.is_file():
                use_git = True
                gitconfig_file = global_gitconfig_file
            # If not found, check ~/.config/git/config (lower priority)
            elif xdg_gitconfig_file.is_file():
                use_git = True
                gitconfig_file = xdg_gitconfig_file
            # If no gitconfig file is found, remove the git_config block from the docker-compose file.
            else:
                use_git = False
                gitconfig_file = None

            if ros_variant.get_version() == "1":
                build_release_cmd = "rosbuild.sh"
                build_debug_cmd = "rosbuild.sh --cmake-args -DCMAKE_BUILD_TYPE=Debug"
                build_relwithdebinfo_cmd = "rosbuild.sh --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo"
                clean_cmd = "catkin clean --yes --verbose --force"
            else:
                build_release_cmd = "rosbuild.sh"
                build_debug_cmd = "rosbuild.sh --mixin debug"
                build_relwithdebinfo_cmd = "rosbuild.sh --mixin rel-with-deb-info"
                clean_cmd = "colcon clean workspace -y"

            service = "devcont"

            items_to_process = {
                ".devcontainer/devcontainer.json": (
                    "vscode/dot_devcontainer.j2",
                    {"service": service, "img_user": img_user, "img_workspace_dir": img_workspace_dir},
                    0o664,
                ),
                ".devcontainer/docker-compose.yaml": (
                    "docker/docker-compose.j2",
                    {
                        "service": service,
                        "img_id": img_id,
                        "workspace_dir": workspace_dir.resolve(),
                        "img_workspace_dir": img_workspace_dir.resolve(),
                        "img_datasets_dir": img_user_home.joinpath("datasets"),
                        "img_ssh_dir": img_user_home.joinpath(".ssh"),
                        "use_git": use_git,
                        "gitconfig_file": gitconfig_file,
                        "img_gitconfig_file": img_user_home.joinpath(".gitconfig"),
                        "ext_uid": f"{os.getuid()}",
                        "ext_upgid": f"{os.getgid()}",
                    },
                    0o775,
                ),
                ".vscode/c_cpp_properties.json": (
                    "vscode/c_cpp_properties.j2",
                    {
                        "c_version": f"c{ros_variant.get_c_version()}",
                        "cpp_version": f"c++{ros_variant.get_cpp_version()}",
                        "ros_distro": ros_variant.get_distro(),
                    },
                    0o664,
                ),
                ".vscode/settings.json": ("vscode/settings.json", None, 0o775),
                ".vscode/tasks.json": (
                    "vscode/tasks.j2",
                    {
                        "build_command_for_release": build_release_cmd,
                        "build_command_for_debug": build_debug_cmd,
                        "build_command_for_relwithdebinfo": build_relwithdebinfo_cmd,
                        "clean_command": clean_cmd,
                    },
                    0o775,
                ),
                "ws.code-workspace": ("vscode/ws.j2", {"ros_distro": ros_variant.get_distro()}, 0o664),
            }

            for key in sorted(items_to_process.keys()):
                item = items_to_process[key]

                dst_item = workspace_dir.joinpath(key).resolve()
                src_item = resources_dir.joinpath(item[0]).resolve()

                if not src_item.exists():
                    raise VscodeProjectCreatorException(
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

        # trim_block removes the first newline after a block (e.g., after {% endif %}).
        # lstrip_blocks strips leading whitespace from the start of a block line.
        except Exception as e:
            self._logger.error(f"{e}")
            raise
