"""
Xena controller handler.
"""
import csv
import io
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Union

from cloudshell.shell.core.driver_context import InitCommandContext, ResourceCommandContext
from cloudshell.traffic.helpers import (
    get_cs_session,
    get_family_attribute,
    get_location,
    get_reservation_id,
    get_resources_from_reservation,
)
from cloudshell.traffic.rest_api_helpers import SandboxAttachments
from cloudshell.traffic.tg import XENA_CHASSIS_MODEL, attach_stats_csv, is_blocking
from trafficgenerator.tgn_utils import ApiType, TgnError
from xenavalkyrie.xena_app import XenaApp, init_xena
from xenavalkyrie.xena_port import XenaPort
from xenavalkyrie.xena_statistics_view import XenaPortsStats, XenaStreamsStats, XenaTpldsStats

from xena_data_model import Xena_Controller_Shell_2G


class XenaHandler:
    """Business logic for all controller shell commands."""

    def __init__(self) -> None:
        """Initialize object variables, actual initialization is performed in initialize method."""
        self.xena: XenaApp = None
        self.logger: logging.Logger = None
        self.service: Xena_Controller_Shell_2G = None

    def initialize(self, context: InitCommandContext, logger: logging.Logger) -> None:
        """Init Xena."""
        self.logger = logger
        self.service = Xena_Controller_Shell_2G.create_from_context(context)
        self.xena = init_xena(ApiType.socket, self.logger, self.service.user)

    def cleanup(self) -> None:
        """Release ports and disconnect."""
        self.xena.session.release_ports()
        self.xena.session.disconnect()

    def load_config(self, context: ResourceCommandContext, xena_configs_folder: str) -> None:
        """Load Xena configuration file, and map and reserve ports."""
        for reserved_port in get_resources_from_reservation(context, f"{XENA_CHASSIS_MODEL}.GenericTrafficGeneratorPort"):
            config = get_family_attribute(context, reserved_port.Name, "Logical Name").strip()
            address = get_location(reserved_port)
            self.logger.debug(f"Configuration {config} will be loaded on Physical location {address}")
            chassis_name = reserved_port.Name.split("/")[0]
            encrypted_password = get_family_attribute(context, chassis_name, f"{XENA_CHASSIS_MODEL}.Password")
            password = get_cs_session(context).DecryptPassword(encrypted_password).Value
            tcp_port = get_family_attribute(context, chassis_name, "Controller TCP Port")
            if not tcp_port:
                tcp_port = "22611"
            ip, module, port = address.split("/")
            chassis = self.xena.session.add_chassis(ip, int(tcp_port), password)
            xena_port = XenaPort(chassis, f"{module}/{port}")
            xena_port.reserve(force=True)
            xena_port.load_config(Path(xena_configs_folder).joinpath(config.replace(".xpc", "") + ".xpc"))

        self.logger.info("Port Reservation Completed")

    def start_traffic(self, blocking: str) -> None:
        """Start traffic on all ports."""
        self.xena.session.clear_stats()
        self.xena.session.start_traffic(is_blocking(blocking))

    def stop_traffic(self) -> None:
        """Stop traffic on all ports."""
        self.xena.session.stop_traffic()

    def get_statistics(self, context: ResourceCommandContext, view_name: str, output_type: str) -> Union[dict, str]:
        """Get statistics for the requested view."""
        stats_obj = view_name_2_object[view_name.lower()](self.xena.session)
        stats_obj.read_stats()
        if output_type.lower().strip() == "json":
            statistics_str = json.dumps(stats_obj.get_flat_stats(), indent=4, sort_keys=True, ensure_ascii=False)
            return json.loads(statistics_str)
        if output_type.lower().strip() == "csv":
            output = io.StringIO()
            captions = [view_name] + list(list(stats_obj.get_flat_stats().values())[0].keys())
            writer = csv.DictWriter(output, captions)
            writer.writeheader()
            for obj_name in stats_obj.get_flat_stats():
                row = {view_name: obj_name}
                row.update((stats_obj.get_flat_stats()[obj_name]))
                writer.writerow(row)
            attach_stats_csv(context, self.logger, view_name, output.getvalue().strip())
            return output.getvalue().strip()
        raise TgnError(f"Output type should be CSV/JSON - got '{output_type}'")

    # pylint: disable=too-many-locals
    def run_rfc(self, context: ResourceCommandContext, test: str, config_file_location: str) -> None:
        """Run RFC test."""
        with open(config_file_location, "r") as file:
            config = json.loads(file.read())
        with tempfile.TemporaryDirectory() as output_path:
            self.logger.debug(f"Temp output path - {output_path}")
            for reserved_port in get_resources_from_reservation(context, f"{XENA_CHASSIS_MODEL}.GenericTrafficGeneratorPort"):
                address = get_location(reserved_port)
                logical_ip = get_family_attribute(context, reserved_port.Name, "Logical Name").strip()
                self.logger.debug(f"RFC logical IP {logical_ip} will be loaded on Physical location {address}")
                chassis, module, port = address.split("/")
                port_handler = [p for p in config["PortHandler"]["EntityList"] if p["IpV4Address"] == logical_ip][0]
                config["ChassisManager"]["ChassisList"][0]["HostName"] = chassis
                port_handler["PortRef"]["ModuleIndex"] = module
                port_handler["PortRef"]["PortIndex"] = port
            temp_config_file_location = Path(output_path).joinpath(Path(config_file_location).name)
            self.logger.debug(f"Temp config file - {temp_config_file_location}")
            with open(temp_config_file_location, "w+") as file:
                json.dump(config, file, indent=2)
            rfc_test_path = Path(self.service.client_install_path).joinpath(f"Valkyrie{test}.exe")
            cmd = [rfc_test_path.as_posix(), "-e", "-c", temp_config_file_location.as_posix(), "-r", output_path]
            self.logger.info(f"Running RFC command - {cmd}")

            rc = subprocess.run(cmd, capture_output=True, check=False)
            self.logger.debug(f"RFC command stdout- {rc.stdout.decode('utf-8')}")
            if rc.returncode > 0:
                raise TgnError(f"Failed to run RFC test - {rc.stdout.decode('utf-8')}")
            output_file = Path(re.findall(b".*PDF.*[(.*)].*", rc.stdout)[0].decode("utf-8").strip())
            quali_api_helper = SandboxAttachments(
                context.connectivity.server_address, context.connectivity.admin_auth_token, self.logger
            )
            quali_api_helper.login()
            quali_api_helper.attach_new_file(
                get_reservation_id(context), file_data=output_file.as_posix(), file_name=output_file.name
            )


view_name_2_object = {"port": XenaPortsStats, "stream": XenaStreamsStats, "tpld": XenaTpldsStats}
