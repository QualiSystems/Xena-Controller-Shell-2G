"""
Xena controller handler.
"""
import csv
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

from cloudshell.shell.core.driver_context import ResourceCommandContext
from cloudshell.traffic.helpers import (
    get_cs_session,
    get_family_attribute,
    get_location,
    get_reservation_id,
    get_resources_from_reservation,
)
from cloudshell.traffic.tg import XENA_CHASSIS_MODEL, TgControllerHandler, attach_stats_csv, is_blocking
from cloudshell.traffic.quali_rest_api_helper import create_quali_api_instance

from trafficgenerator.tgn_utils import ApiType, TgnError
from xenavalkyrie.xena_app import init_xena
from xenavalkyrie.xena_port import XenaPort
from xenavalkyrie.xena_statistics_view import XenaPortsStats, XenaStreamsStats, XenaTpldsStats

from xena_data_model import Xena_Controller_Shell_2G


class XenaHandler(TgControllerHandler):
    """Business logic for all controller shell commands."""

    def __init__(self):
        self.xena = None

    def initialize(self, context, logger):
        service = Xena_Controller_Shell_2G.create_from_context(context)
        super().initialize(context, logger, service)
        self.xena = init_xena(ApiType.socket, self.logger, self.service.user)

    def cleanup(self):
        self.xena.session.release_ports()
        self.xena.session.disconnect()

    def load_config(self, context, xena_configs_folder):

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
            xena_port.load_config(Path(xena_configs_folder).parent.joinpath(config.replace(".xpc", "") + ".xpc"))

        self.logger.info("Port Reservation Completed")

    def start_traffic(self, context, blocking):
        self.xena.session.clear_stats()
        self.xena.session.start_traffic(is_blocking(blocking))

    def stop_traffic(self):
        self.xena.session.stop_traffic()

    def get_statistics(self, context, view_name, output_type):

        stats_obj = view_name_2_object[view_name.lower()](self.xena.session)
        stats_obj.read_stats()
        if output_type.lower().strip() == "json":
            statistics_str = json.dumps(stats_obj.get_flat_stats(), indent=4, sort_keys=True, ensure_ascii=False)
            return json.loads(statistics_str)
        elif output_type.lower().strip() == "csv":
            output = io.StringIO()
            captions = [view_name] + list(list(stats_obj.get_flat_stats().values())[0].keys())
            writer = csv.DictWriter(output, captions)
            writer.writeheader()
            for obj_name in stats_obj.get_flat_stats():
                d = {view_name: obj_name}
                d.update((stats_obj.get_flat_stats()[obj_name]))
                writer.writerow(d)
            attach_stats_csv(context, self.logger, view_name, output.getvalue().strip())
            return output.getvalue().strip()
        else:
            raise TgnError(f"Output type should be CSV/JSON - got '{output_type}'")

    def run_rfc(self, context: ResourceCommandContext, test: str, config_file_location: str) -> None:
        with open(config_file_location, "r") as file:
            config = json.loads(file.read())
        output_path = tempfile.TemporaryDirectory()
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
        temp_config_file_location = Path(output_path.name).joinpath(Path(config_file_location).name)
        self.logger.debug(f"Temp config file - {temp_config_file_location}")
        with open(temp_config_file_location, "w+") as file:
            json.dump(config, file, indent=2)
        rfc_test_path = Path(self.service.client_install_path).joinpath(f"Valkyrie{test}.exe")
        cmd = [rfc_test_path.as_posix(), "-e", "-c", temp_config_file_location.as_posix(), "-r", output_path.name]
        self.logger.info(f"Running RFC command - {cmd}")
        rc = subprocess.run(cmd, capture_output=True)
        self.logger.debug(f"RFC command stdout- {rc.stdout}")
        if rc.returncode > 0:
            raise TgnError(f"Failed to run RFC test - {rc.stdout}")
        output_file = Path(re.findall(b".*PDF.*\[(.*)\].*", rc.stdout)[0].decode("utf-8"))
        quali_api_helper = create_quali_api_instance(context, self.logger)
        quali_api_helper.login()
        quali_api_helper.attach_new_file(
            get_reservation_id(context), file_data=open(output_file.as_posix(), "br"), file_name=output_file.name
        )


view_name_2_object = {"port": XenaPortsStats, "stream": XenaStreamsStats, "tpld": XenaTpldsStats}
