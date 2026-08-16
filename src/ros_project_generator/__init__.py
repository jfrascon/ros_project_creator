"""
ros-project-generator

This package provides tools for creating and configuring ROS-based development projects
with Docker, VS Code, CI/CD and ROS best practices.

Public API:

- `RosProjectCreator`: creates a ROS project from templates, including workspace
  structure, Docker setup through `robotics_dockers`, optional VS Code integration,
  and pre-commit support.

- `VscodeProjectCreator`: creates or updates the VS Code `.devcontainer` environment
  configuration for an existing project.

Usage example:

    from pathlib import Path
    from ros_project_generator import RosProjectCreator

    creator = RosProjectCreator(
        project_id="myrobot",
        project_dir=Path("/home/user/dev/myrobot"),
        user="developer",
        user_id="1000",
        primary_group="developer",
        primary_group_id="1000",
        ros_distro="humble",
        base_img="eutrob/eut_ros:humble",
        img_id="myrobot:latest",
        use_vscode_project=True,
        use_pre_commit=True,
    )

Note: Internal utilities used by this package (e.g. `Utilities`, logging helpers)
are not part of the public API and should not be used directly.
"""

__all__ = ['RosProjectCreator', 'VscodeProjectCreator']


def __getattr__(name: str):
    if name == 'RosProjectCreator':
        from .ros_project_generator import RosProjectCreator

        return RosProjectCreator

    if name == 'VscodeProjectCreator':
        from .vscode_project_creator import VscodeProjectCreator

        return VscodeProjectCreator

    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
