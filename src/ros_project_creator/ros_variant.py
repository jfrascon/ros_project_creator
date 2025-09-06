from pathlib import Path

from ros_project_creator.utilities import Utilities


class RosVariant:

    def __init__(self, ros_distro: str, ros_variants_yaml_file: Path):
        ros_distro = Utilities.clean_str(ros_distro)
        Utilities.assert_non_empty(ros_distro, "ROS distro must be a non-empty string")

        Utilities.assert_file_existence(
            ros_variants_yaml_file, f"File '{ros_variants_yaml_file.resolve()}' is required"
        )

        # Check if the ros_distro provided by the user is supported by the configuration provided in the resources.
        ros_variants = Utilities.load_yaml(ros_variants_yaml_file)
        Utilities.assert_non_empty(
            ros_variants, f"No ROS variants found in the file '{ros_variants_yaml_file.resolve()}'"
        )

        if ros_distro in ros_variants:
            self._ros_variant = ros_variants[ros_distro]
        else:
            supported_ros_distros = ", ".join(
                f"{ros_distro} (ros{data['ros_version']})" for ros_distro, data in ros_variants.items()
            )
            raise Exception(f"Found ROS distro '{ros_distro}'. Allowed ROS distros: {supported_ros_distros}")

    def get_c_version(self) -> str:
        """
        Returns the C version associated with the ROS variant.
        Returns:
            str: The C version.
        """
        return self._ros_variant["c_version"]

    def get_cpp_version(self) -> str:
        """
        Returns the C++ version associated with the ROS variant.
        Returns:
            str: The C++ version.
        """
        return self._ros_variant["cpp_version"]

    def get_distro(self) -> str:
        """
        Returns the ROS distro.
        Returns:
            str: The ROS distro.
        """
        return self._ros_variant["ros_distro"]

    def get_ubuntu_version(self) -> str:
        """
        Returns the Ubuntu distro
        Returns:
            str: The Ubuntu distro
        """
        return self._ros_variant["ubuntu_version"]

    def get_version(self) -> str:
        """
        Returns the ROS version.
        Returns:
            str: The ROS version.
        """
        return self._ros_variant["ros_version"]

    def get_python_version(self) -> str:
        """
        Returns the Python version associated with the Ubuntu base for this ROS distro.
        Returns:
            str: The Python version (e.g., '3.8', '3.10', '3.12').
        """
        return self._ros_variant["python_version"]
