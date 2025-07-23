#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

import argcomplete

from ros_project_creator.utilities import Utilities
from ros_project_creator.vscode_project_creator import VscodeProjectCreator, VscodeProjectCreatorException


def main():
    try:
        if os.geteuid() == 0:
            raise RuntimeError('ERROR: This script must not be run with sudo or as root')

        resources_path = Path(__file__).parent.joinpath('resources')
        ros_variants = Utilities.load_yaml(resources_path.joinpath('ros', 'ros_variants.yaml'))
        Utilities.assert_non_empty(
            ros_variants, f"No ROS variants found in the resource path '{resources_path.resolve()}'"
        )
        supported_ros_distros = ', '.join(
            f'{ros_distro} (ros{data["ros_version"]})' for ros_distro, data in ros_variants.items()
        )

        parser = argparse.ArgumentParser(
            description='Creates a new VSCode project based on templates',
            allow_abbrev=False,  # Disable prefix matching
            add_help=False,  # Add custom help message
            formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=35),
        )

        parser.add_argument('ros_distro', type=str, help=f'ROS distro to use: {supported_ros_distros}')

        parser.add_argument(
            'img_id', type=str, help='ID of the Docker image that VSCode will use to create a container'
        )

        parser.add_argument('img_user', type=str, help='User to use inside the container')

        parser.add_argument('workspace_dir', type=str, help='Path to the VSCode workspace')

        parser.add_argument('img_workspace_dir', type=str, help='Path to the workspace in the image')

        parser.add_argument(
            '--no_console_log',
            action='store_true',
            help='Disable logging to console. Console logging is enabled by default',
            default=False,
        )

        parser.add_argument('--log_file', type=str, help='File to log output', default='')

        parser.add_argument('--log_level', type=str, help='Logging level (Default is DEBUG)', default='DEBUG')

        parser.add_argument(
            '-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit'
        )

        argcomplete.autocomplete(parser)

        args = parser.parse_args()

        VscodeProjectCreator(
            Utilities.clean_str(args.ros_distro),  # type: ignore
            Utilities.clean_str(args.img_id),  # type: ignore
            Utilities.clean_str(args.img_user),  # type: ignore
            Path(Utilities.clean_str(args.workspace_dir)),  # type: ignore
            Path(Utilities.clean_str(args.img_workspace_dir)),  # type: ignore
            not args.no_console_log,  # parameter is used_console_log, so it is inverted # type: ignore
            args.log_file,
            args.log_level,
        )
    except VscodeProjectCreatorException:
        sys.exit(1)
    except Exception as e:
        print(f'{e}', file=sys.stderr)
        # traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
