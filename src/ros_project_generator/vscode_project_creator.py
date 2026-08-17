import shutil
from pathlib import Path

import yaml

from ros_project_generator.logging_utils import create_logger
from ros_project_generator.resource_installer import ResourceInstaller, ResourceSpec
from ros_project_generator.ros_variant import RosVariant
from ros_project_generator.utilities import Utilities


class VscodeProjectCreatorException(Exception):
    """Base exception for errors while creating the VS Code files."""


class VscodeProjectCreator:
    """Create editor files around the ROS project's Compose file.

    The production and Dev Container copies start with the same content, but
    they are separate physical files in the generated project. A developer can
    therefore customize the Dev Container without changing production.
    """

    def __init__(
        self,
        project_id: str,
        ros_distro: str,
        workspace_dir: Path,
        source_compose_file: Path,
        use_console_log: bool = True,
        log_file: str = '',
        log_level: str = 'DEBUG',
    ):
        self._logger = create_logger(
            name='VscodeProjectCreator', use_console_log=use_console_log, log_file=log_file, log_level=log_level
        )

        try:
            self._resources_dir = Path(__file__).parent.joinpath('resources')
            Utilities.assert_dir_existence(self._resources_dir, f"Path '{self._resources_dir}' is required")

            self._project_id = Utilities.clean_str(project_id)
            Utilities.assert_non_empty(self._project_id, 'Project id must be a non-empty string')

            if not Utilities.is_valid_project_id(self._project_id):
                raise VscodeProjectCreatorException(
                    'Project id must start with a lowercase letter or digit and contain only '
                    f"lowercase letters, digits, '-' and '_'; found '{self._project_id}'"
                )

            ros_variant_yaml_file = self._resources_dir.joinpath('ros/ros_variants.yaml')
            self._ros_variant = RosVariant(ros_distro, ros_variant_yaml_file)
            self._assert_ros2_variant()

            if not workspace_dir:
                raise VscodeProjectCreatorException('Workspace path must be provided')
            self._workspace_dir = workspace_dir.expanduser().resolve()

            if not source_compose_file:
                raise VscodeProjectCreatorException('Source Compose file must be provided')
            self._source_compose_file = source_compose_file.expanduser().resolve()
            Utilities.assert_file_existence(
                self._source_compose_file, f"ROS project Compose file '{self._source_compose_file}' is required"
            )

            # Dev Containers needs the service name in devcontainer.json. Read
            # it from the generated Compose file instead of reproducing the
            # naming rule owned by robotics_dockers.
            self._compose_service, self._image_name = self._read_single_compose_service()
            self._install_items()
        except VscodeProjectCreatorException as error:
            self._logger.error(f'{error}')
            raise
        except Exception as error:
            self._logger.error(f'{error}')
            raise VscodeProjectCreatorException(f'{error}') from error

    def _assert_ros2_variant(self) -> None:
        if self._ros_variant.get_version() != 2:
            raise VscodeProjectCreatorException(
                f"ROS distro '{self._ros_variant.get_distro()}' is ROS {self._ros_variant.get_version()}. "
                'ros-project-generator currently supports ROS 2 only.'
            )

    def _read_single_compose_service(self) -> tuple[str, str]:
        try:
            compose_data = yaml.safe_load(self._source_compose_file.read_text())
        except yaml.YAMLError as error:
            raise VscodeProjectCreatorException(
                f"Compose file '{self._source_compose_file}' is not valid YAML: {error}"
            ) from error

        if not isinstance(compose_data, dict):
            raise VscodeProjectCreatorException(
                f"Compose file '{self._source_compose_file}' must contain a YAML mapping"
            )

        services = compose_data.get('services')
        if not isinstance(services, dict) or len(services) != 1:
            raise VscodeProjectCreatorException(
                f"Compose file '{self._source_compose_file}' must define exactly one service"
            )

        service_name = next(iter(services))
        service = services[service_name]
        if not isinstance(service, dict) or not isinstance(service.get('image'), str) or not service['image'].strip():
            raise VscodeProjectCreatorException(
                f"Service '{service_name}' in '{self._source_compose_file}' must name one Docker image"
            )

        return service_name, service['image'].strip()

    def _create_items_to_install(self) -> list[ResourceSpec]:
        return [
            ResourceSpec.template(
                '.devcontainer/devcontainer.json',
                'vscode/devcontainer.json.j2',
                {'service': self._compose_service, 'img_workspace_dir': '/workspace'},
            ),
            ResourceSpec.template(
                '.devcontainer/code-devcont',
                'vscode/code-devcont.j2',
                {'image_name': self._image_name, 'project_id': self._project_id},
                executable=True,
            ),
            ResourceSpec.template(
                '.devcontainer/devcont',
                'vscode/devcont.j2',
                {'image_name': self._image_name, 'project_id': self._project_id},
                executable=True,
            ),
            ResourceSpec.template(
                '.vscode/c_cpp_properties.json',
                'vscode/c_cpp_properties.json.j2',
                {
                    'c_version': f'c{self._ros_variant.get_c_version()}',
                    'cpp_version': f'c++{self._ros_variant.get_cpp_version()}',
                    'ros_distro': self._ros_variant.get_distro(),
                },
            ),
            ResourceSpec.template('.vscode/tasks.json', 'vscode/tasks.json.j2', {}, executable=True),
            ResourceSpec.template(
                'ws.code-workspace',
                'vscode/ws.code-workspace.j2',
                {
                    'project_id': self._project_id,
                    'ros_distro': self._ros_variant.get_distro(),
                    'python_version': self._ros_variant.get_python_version(),
                },
            ),
        ]

    def _install_items(self) -> None:
        ResourceInstaller(
            resources_dir=self._resources_dir,
            target_dir=self._workspace_dir,
            logger=self._logger,
            exception_type=VscodeProjectCreatorException,
            replace_existing=True,
        ).install(self._create_items_to_install())

        # The ROS project owns both Compose files. They start byte-for-byte
        # equal, but this physical copy lets each developer customize the Dev
        # Container without changing the production configuration.
        devcontainer_compose_file = self._workspace_dir.joinpath('.devcontainer/docker-compose.yaml')
        shutil.copyfile(self._source_compose_file, devcontainer_compose_file)
        devcontainer_compose_file.chmod(0o664)
