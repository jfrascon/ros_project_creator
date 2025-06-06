#!/usr/bin/env python3
import argparse
import argcomplete
import os
from pathlib import Path
import sys

from ros_project_creator.ros_project_creator import RosProjectCreator
from ros_project_creator.ros_project_creator import RosProjectCreatorException
from ros_project_creator.utilities import Utilities


def main():
    try:
        if os.geteuid() == 0:
            raise RuntimeError("ERROR: This script must not be run with sudo or as root")

        resources_dir = Path(__file__).parent.joinpath("resources")
        ros_variants = Utilities.load_yaml(resources_dir.joinpath("ros", "ros_variants.yaml"))
        Utilities.assert_non_empty(
            ros_variants, f"No ROS variants found in the resource path '{resources_dir.resolve()}'"
        )
        supported_ros_distros = ", ".join(
            f"{ros_distro} (ros{data['ros_version']})" for ros_distro, data in ros_variants.items()
        )

        parser = argparse.ArgumentParser(
            description="Creates a new ROS project based on templates",
            allow_abbrev=False,  # Disable prefix matching
            add_help=False,  # Add custom help message
            formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=40),
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

        entrypoint_group = parser.add_mutually_exclusive_group()

        entrypoint_group.add_argument(
            "--use-base-img-entrypoint",
            action="store_true",
            help="The image will inherit the base image's entrypoint, if any. Do not use this option if you set a custom entrypoint",
        )

        entrypoint_group.add_argument(
            "--entrypoint",
            type=str,
            metavar="ENTRYPOINT_SCRIPT",
            help="Path to a custom entrypoint script to include in the Docker image (replaces the default entrypoint script)",
        )

        environment_group = parser.add_mutually_exclusive_group()

        environment_group.add_argument(
            "--no-environment",
            action="store_true",
            help="Do not use an environment script. Do not use this option if you set a custom environment script",
        )

        environment_group.add_argument(
            "--environment",
            type=str,
            metavar="ENVIRONMENT_SCRIPT",
            help="Path to a custom environment script to include in the Docker image (replaces the default environment script)",
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

        if args.entrypoint:
            entrypoint = Path(args.entrypoint).expanduser().resolve()

            if not entrypoint.is_file():
                raise FileNotFoundError(
                    f"Custom entrypoint file '{entrypoint}' does not exist or is not a regular file"
                )
        else:
            entrypoint = None

        if args.environment:
            environment = Path(args.environment).expanduser().resolve()

            if not environment.is_file():
                raise FileNotFoundError(
                    f"Custom environment file '{environment}' does not exist or is not a regular file"
                )
        else:
            environment = None

        RosProjectCreator(
            args.project_id,
            Path(args.project_dir),
            args.ros_distro,
            args.base_img,
            args.img_user,
            args.img_id,
            entrypoint,
            args.use_base_img_entrypoint,
            environment,
            not args.no_environment,  # parameter is use_environment, so it is inverted
            not args.no_vscode,  # parameter is use_vscode_project, so it is inverted
            not args.no_pre_commit,  # parameter is used_pre_commit, so it is inverted
            not args.no_console_log,  # parameter is used_console_log, so it is inverted
            args.log_file,
            args.log_level,
        )
    except RosProjectCreatorException:
        sys.exit(1)
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        # traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
