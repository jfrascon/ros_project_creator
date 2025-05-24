#!/usr/bin/env python3

from pathlib import Path
import os

from jinja2 import Environment, FileSystemLoader

from ros_project_creator.colorizedlogs import ColorizedLogger

from ros_project_creator.ros_variant import RosVariant
from ros_project_creator.utilities import Utilities


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
            workspace_dir (Path): Path to the VSCode workspace (e.g. '/path/to/robproj')
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
            self._resources_dir = Path(__file__).parent.joinpath("resources")
            Utilities.assert_dir_existence(self._resources_dir, f"Path '{self._resources_dir.resolve()}' is required")

            # Get the the ros_variant (ros_distro, ros_version, cpp_version, c_version) associated to the passed
            # ros_distro.
            ros_variant_yaml_file = self._resources_dir.joinpath("ros", "ros_variants.yaml")
            self._ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)

            self._img_id = Utilities.clean_str(img_id)
            Utilities.assert_non_empty(self._img_id, "Image id must be a non-empty string")

            self._img_user = Utilities.clean_str(img_user)
            Utilities.assert_non_empty(self._img_user, "Image user must be a non-empty string")

            if not workspace_dir:
                raise Exception("Workspace path must be provided")

            # If the workspace directory does not exist, it does not matter, it will be creater later, in the run
            # method.
            self._workspace_dir = workspace_dir

            if not img_workspace_dir:
                raise Exception("Image workspace path must be provided")

            self._img_workspace_dir = img_workspace_dir

            self._check_templates_existance()
        except Exception as e:
            self._logger.error(f"{e}")
            raise

    def _check_templates_existance(self) -> None:
        self._vscode_templates_dir = self._resources_dir.joinpath("vscode")
        Utilities.assert_dir_existence(
            self._vscode_templates_dir, f"Directory '{self._vscode_templates_dir}' is required"
        )

        self._vscode_workspace_template = self._vscode_templates_dir.joinpath("ws.j2")
        Utilities.assert_file_existence(
            self._vscode_workspace_template, f"Template '{self._vscode_workspace_template}' is required"
        )

        self._vscode_settings_template = self._vscode_templates_dir.joinpath("settings.json")
        Utilities.assert_file_existence(
            self._vscode_settings_template, f"Template '{self._vscode_settings_template}' is required"
        )

        self._vscode_c_cpp_properties_template = self._vscode_templates_dir.joinpath("c_cpp_properties.j2")
        Utilities.assert_file_existence(
            self._vscode_c_cpp_properties_template,
            f"Template '{self._vscode_c_cpp_properties_template}' is required",
        )

        self._vscode_tasks_template = self._vscode_templates_dir.joinpath("tasks.j2")
        Utilities.assert_file_existence(
            self._vscode_tasks_template, f"Template '{self._vscode_tasks_template}' is required"
        )

        self._vscode_devcontainer_template = self._vscode_templates_dir.joinpath("devcontainer.j2")
        Utilities.assert_file_existence(
            self._vscode_devcontainer_template, f"Template '{self._vscode_devcontainer_template}' is required"
        )

        self._docker_templates_dir = self._resources_dir.joinpath("docker")
        Utilities.assert_dir_existence(
            self._docker_templates_dir, f"Directory '{self._docker_templates_dir.resolve()}' is required"
        )

        self._docker_compose_template = self._docker_templates_dir.joinpath("docker-compose.j2")
        Utilities.assert_file_existence(
            self._docker_compose_template,
            f"Template '{self._docker_compose_template.resolve()}' is required",
        )

    def _create(self) -> None:
        vscode_devcontainer_dir = self._workspace_dir.joinpath(".devcontainer")
        Utilities.mkdir(vscode_devcontainer_dir, 0o755, self._logger.info)

        vscode_dir = self._workspace_dir.joinpath(".vscode")
        Utilities.mkdir(vscode_dir, 0o755, self._logger.info)

        # trim_block removes the first newline after a block (e.g., after {% endif %}).
        # lstrip_blocks strips leading whitespace from the start of a block line.
        jinja2_env = Environment(
            loader=FileSystemLoader(self._vscode_templates_dir), trim_blocks=True, lstrip_blocks=True
        )

        vscode_workspace_file = self._workspace_dir.joinpath("ws.code-workspace")
        Utilities.install_template(
            jinja2_env,
            self._vscode_workspace_template,
            {"ros_distro": self._ros_variant.get_distro()},
            vscode_workspace_file,
            0o644,
            self._logger.info,
        )

        vscode_settings_file = vscode_dir.joinpath("settings.json")
        Utilities.copy_file(self._vscode_settings_template, vscode_settings_file, 0o644, self._logger.info)

        vscode_c_cpp_properties_file = vscode_dir.joinpath("c_cpp_properties.json")
        Utilities.install_template(
            jinja2_env,
            self._vscode_c_cpp_properties_template,
            {
                "c_version": f"c{self._ros_variant.get_c_version()}",
                "cpp_version": f"c++{self._ros_variant.get_cpp_version()}",
                "ros_distro": self._ros_variant.get_distro(),
            },
            vscode_c_cpp_properties_file,
            0o644,
            self._logger.info,
        )

        vscode_tasks_file = vscode_dir.joinpath("tasks.json")
        if self._ros_variant.get_version() == "1":
            build_release_cmd = "rosbuild.sh"
            build_debug_cmd = "rosbuild.sh --cmake-args -DCMAKE_BUILD_TYPE=Debug"
            build_relwithdebinfo_cmd = "rosbuild.sh --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo"
            clean_cmd = "catkin clean --yes --verbose --force"
        else:
            build_release_cmd = "rosbuild.sh"
            build_debug_cmd = "rosbuild.sh --mixin debug"
            build_relwithdebinfo_cmd = "rosbuild.sh --mixin rel-with-deb-info"
            clean_cmd = "colcon clean workspace -y"

        Utilities.install_template(
            jinja2_env,
            self._vscode_tasks_template,
            {
                "build_command_for_release": build_release_cmd,
                "build_command_for_debug": build_debug_cmd,
                "build_command_for_relwithdebinfo": build_relwithdebinfo_cmd,
                "clean_command": clean_cmd,
            },
            vscode_tasks_file,
            0o644,
            self._logger.info,
        )

        service = "devcont"

        vscode_devcontainer_file = vscode_devcontainer_dir.joinpath("devcontainer.json")
        Utilities.install_template(
            jinja2_env,
            self._vscode_devcontainer_template,
            {"service": service, "img_user": self._img_user, "img_workspace_dir": self._img_workspace_dir},
            vscode_devcontainer_file,
            0o644,
            self._logger.info,
        )

        # Render the templates for Docker.
        # --------------------------------
        # trim_block removes the first newline after a block (e.g., after {% endif %}).
        # lstrip_blocks strips leading whitespace from the start of a block line.
        jinja2_env = Environment(
            loader=FileSystemLoader(self._docker_templates_dir), trim_blocks=True, lstrip_blocks=True
        )

        docker_compose_file = vscode_devcontainer_dir.joinpath("docker-compose.yaml")
        img_user_home = Path("/root") if self._img_user == "root" else Path(f"/home/{self._img_user}")

        # Get git config for the user running the project configuration tool and write it to the docker-compose file,
        # in the volumes section.
        home = Path.home()
        global_gitconfig_file = home.joinpath(".gitconfig")
        xdg_gitconfig_file = home.joinpath(".config", "git", "config")

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
            gitconfig_file = Path("")

        Utilities.install_template(
            jinja2_env,
            self._docker_compose_template,
            {
                "service": service,
                "img_id": self._img_id,
                "workspace_dir": self._workspace_dir.resolve(),
                "img_workspace_dir": self._img_workspace_dir.resolve(),
                "img_datasets_dir": img_user_home.joinpath("datasets").resolve(),
                "img_ssh_dir": img_user_home.joinpath(".ssh").resolve(),
                "use_git": use_git,
                "gitconfig_file": gitconfig_file.resolve(),
                "img_gitconfig_file": img_user_home.joinpath(".gitconfig").resolve(),
                "ext_uid": f"{os.getuid()}",
                "ext_upgid": f"{os.getgid()}",
            },
            docker_compose_file,
            0o644,
            self._logger.info,
        )

    def create(self):
        try:
            # Perform all checks before creating paths or installing files. This approach reduces the likelihood of
            # ending up with an incomplete installation if an error occurs during the installation process.
            self._logger.info("Creating VSCode project...")

            if not self._workspace_dir.exists():
                Utilities.mkdir(self._workspace_dir, 0o755, self._logger.info)

            self._create()
        except Exception as e:
            self._logger.error(f"{e}")
            raise
