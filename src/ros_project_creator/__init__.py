"""
ros_project_creator

This package provides tools for creating and configuring ROS-based development projects
with Docker, VSCode, CI/CD and ROS best practices.

Public API:

- `RosProjectCreator`: creates a ROS project from templates, including Docker setup,
  workspace structure, optional VSCode integration, and pre-commit support.

- `VscodeProjectCreator`: creates or updates the VSCode `.devcontainer` environment
  configuration for an existing project.

Usage example:

    from pathlib import Path
    from ros_project_creator import RosProjectCreator

    creator = RosProjectCreator(
        project_id="myrobot",
        project_path=Path("/home/user/dev/myrobot"),
        ros_distro="humble",
        base_img="eutrob/eut_ros:humble",
        img_id="myrobot:latest",
        user_group="eutrob:eutrob",
        workdir="/home/eutrob",
        use_base_img_entrypoint=True,
        entrypoint=None,
        resources_path=None, # If you want to use the default resources path, set it to None
        use_vscode_project=True,
    )

    creator.run()

Note: Internal utilities used by this package (e.g. `Utilities`, `ColorizedLogger`)
are not part of the public API and should not be used directly.
"""

from .create_ros_project import RosProjectCreator
from .create_vscode_project import VscodeProjectCreator

__all__ = ["RosProjectCreator", "VscodeProjectCreator"]
