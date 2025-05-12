#!/usr/bin/env python3
import argparse
import argcomplete
from pathlib import Path
import sys


from ros_project_creator.ros_project_creator import RosProjectCreator
from ros_project_creator.ros_project_creator import RosProjectCreatorException
from ros_project_creator.docker_platform import DockerPlaform
from ros_project_creator.utilities import Utilities


def main():

    def build_platform_help(platforms: dict[str, DockerPlaform]) -> str:
        lines = ["Platform to use for the resulting Docker image (e.g. 'linux/amd64').", "Supported platforms:"]

        for platform in sorted(platforms.values(), key=lambda p: p.get_id()):
            lines.append(f"  {platform.get_id():<14} - {platform.get_description()}")

        return "\n".join(lines)

    try:
        # if os.geteuid() == 0:
        #     raise RuntimeError("ERROR: This script must not be run with sudo or as root")

        resources_dir = Path(__file__).parent.joinpath("resources")
        ros_variants = Utilities.load_yaml(resources_dir.joinpath("ros", "ros_variants.yaml"))
        Utilities.assert_non_empty(
            ros_variants, f"No ROS variants found in the resource path '{resources_dir.resolve()}'"
        )
        supported_ros_distros = ", ".join(
            f"{ros_distro} (ros{data['ros_version']})" for ros_distro, data in ros_variants.items()
        )

        docker_supported_platforms = {
            "linux/amd64": DockerPlaform(
                "linux/amd64", ["x86_64", "amd64"], "64-bit x86_64 (e.g. Intel/AMD PCs and servers)"
            ),
            "linux/arm64": DockerPlaform("linux/arm64", ["aarch64", "arm64"], "64-bit ARM (e.g. Raspberry Pi 4)"),
            "linux/arm/v7": DockerPlaform(
                "linux/arm/v7", ["armv7l", "armv7", "armhf"], "32-bit ARMv7-A (e.g. Raspberry Pi 2/3 with 32-bit OS)"
            ),
        }

        parser = argparse.ArgumentParser(
            description="Creates a new ROS project based on templates",
            allow_abbrev=False,  # Disable prefix matching
            add_help=False,  # Add custom help message
            formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=35),
            # formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=35),
        )

        parser.add_argument(
            "project_id", type=str, help="Short, descriptive project identifier for internal reference (e.g. 'robproj')"
        )

        parser.add_argument(
            "project_dir",
            type=str,
            help="Path where the project will be created (e.g. '~/projects/robproj')",
        )

        parser.add_argument("ros_distro", type=str, help=f"ROS distro to use: {supported_ros_distros}")

        parser.add_argument("base_img", type=str, help="Base Docker image to use (e.g. 'eutrob/eut_ros:humble')")

        parser.add_argument("platform", type=str, help=build_platform_help(docker_supported_platforms))

        parser.add_argument(
            "img_user",
            type=str,
            help="Active user to use in the resulting Docker image",
        )

        parser.add_argument(
            "--img-id",
            type=str,
            default=None,
            help="ID of the resulting Docker image (e.g. 'robproj:humble'). If not set, defaults to '<project-id>:latest'",
        )

        parser.add_argument("--no-vscode", action="store_true", help="Do not create VSCode project")

        parser.add_argument("--no-pre-commit", action="store_true", help="Do not use pre-commit hooks")

        parser.add_argument(
            "--no-console-log",
            action="store_true",
            help="Disable logging to console. Console logging is enabled by default",
        )

        parser.add_argument("--log-file", type=str, help="File to log output", default="")

        parser.add_argument("--log-level", type=str, help="Logging level (Default is DEBUG)", default="DEBUG")

        parser.add_argument(
            "-h", "--help", action="help", default=argparse.SUPPRESS, help="Show this help message and exit"
        )

        argcomplete.autocomplete(parser)
        args = parser.parse_args()

        ros_project_creator = RosProjectCreator(
            args.project_id,
            Path(args.project_dir),
            args.ros_distro,
            args.base_img,
            docker_supported_platforms,
            args.platform,
            args.img_id,
            args.img_user,
            not args.no_vscode,  # parameter is used_vscode_project, so it is inverted
            not args.no_pre_commit,  # parameter is used_pre_commit, so it is inverted
            not args.no_console_log,  # parameter is used_console_log, so it is inverted
            args.log_file,
            args.log_level,
        )

        ros_project_creator.create()
    except RosProjectCreatorException:
        sys.exit(1)
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        # traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
