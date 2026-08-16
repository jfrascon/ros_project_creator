#!/usr/bin/env python3
import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import argcomplete

from ros_project_generator.ros_project_generator import RosProjectCreator, RosProjectCreatorException
from ros_project_generator.utilities import Utilities


def main(argv: Optional[Sequence[str]] = None, prog: Optional[str] = None) -> None:
    try:
        if os.geteuid() == 0:
            raise RuntimeError('This script must not be run with sudo or as root')

        resources_dir = Path(__file__).parent.joinpath('resources')
        ros_variants = Utilities.load_yaml(resources_dir.joinpath('ros', 'ros_variants.yaml'))
        Utilities.assert_non_empty(
            ros_variants, f"No ROS variants found in the resource path '{resources_dir.resolve()}'"
        )
        supported_ros_distros = ', '.join(
            f'{ros_distro} (ros{data["ros_version"]})' for ros_distro, data in ros_variants.items()
        )

        parser = argparse.ArgumentParser(
            prog=prog,
            description='Creates a new ROS project based on templates',
            allow_abbrev=False,  # Disable prefix matching
            add_help=False,  # Add custom help message
            formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=40),
            # formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=35),
        )

        parser.add_argument(
            'project_id',
            type=str,
            help="Short, descriptive project identifier for internal reference (e.g. 'botzilla')",
        )

        parser.add_argument(
            'project_dir', type=str, help="Path where the project will be created (e.g. '~/projects/botzilla')"
        )

        parser.add_argument('ros_distro', type=str, metavar='ros-distro', help=f'ROS distro: {supported_ros_distros}')

        parser.add_argument(
            '--base-img',
            type=str,
            default=None,
            metavar='IMAGE',
            help='Base Docker image. Default: the Ubuntu version associated with ros-distro.',
        )

        parser.add_argument(
            '--img-id',
            type=str,
            default=None,
            help=(
                "ID of the resulting Docker image (e.g. 'botzilla:jazzy'). If not set, defaults to "
                "'<project-id>:latest'"
            ),
        )

        parser.add_argument(
            '--nvidia', action='store_true', dest='use_host_nvidia_driver', help="Use host's NVIDIA driver"
        )

        parser.add_argument('--no-vscode', action='store_true', help='Do not create VS Code project')

        parser.add_argument('--no-pre-commit', action='store_true', help='Do not use pre-commit hooks')

        parser.add_argument(
            '--no-console-log',
            action='store_true',
            help='Disable logging to console. Console logging is enabled by default',
        )

        parser.add_argument('--log-file', type=str, help='File to log output', default='')

        parser.add_argument('--log-level', type=str, help='Logging level (Default is DEBUG)', default='DEBUG')

        parser.add_argument(
            '-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit'
        )

        argcomplete.autocomplete(parser)
        args = parser.parse_args(argv)

        RosProjectCreator(
            project_id=args.project_id,
            project_dir=Path(args.project_dir),
            ros_distro=args.ros_distro,
            base_img=args.base_img,
            img_id=args.img_id,
            use_host_nvidia_driver=args.use_host_nvidia_driver,
            use_vscode_project=not args.no_vscode,
            use_pre_commit=not args.no_pre_commit,
            use_console_log=not args.no_console_log,
            log_file=args.log_file,
            log_level=args.log_level,
        )
    except RosProjectCreatorException:
        sys.exit(1)
    except Exception as e:
        print(f'{e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
