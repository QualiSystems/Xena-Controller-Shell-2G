"""
Xena controller handler.
"""
import csv
import io
import json
from os import path

from cloudshell.traffic.helpers import get_cs_session, get_family_attribute, get_location, get_resources_from_reservation
from cloudshell.traffic.tg import XENA_CHASSIS_MODEL, TgControllerHandler, attach_stats_csv, is_blocking
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
            xena_port.load_config(path.join(xena_configs_folder, config.replace(".xpc", "")) + ".xpc")

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


view_name_2_object = {"port": XenaPortsStats, "stream": XenaStreamsStats, "tpld": XenaTpldsStats}
