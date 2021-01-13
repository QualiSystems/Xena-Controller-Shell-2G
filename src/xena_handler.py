
from os import path
import json
import csv
import io

from cloudshell.traffic.tg_helper import get_address, is_blocking, get_family_attribute
from cloudshell.traffic.common import get_resources_from_reservation
from cloudshell.traffic.tg import TgControllerHandler, attach_stats_csv

from trafficgenerator.tgn_utils import ApiType
from xenavalkyrie.xena_app import init_xena
from xenavalkyrie.xena_port import XenaPort
from xenavalkyrie.xena_statistics_view import XenaPortsStats, XenaStreamsStats, XenaTpldsStats

from xena_data_model import Xena_Controller_Shell_2G


class XenaHandler(TgControllerHandler):

    def initialize(self, context, logger):
        service = Xena_Controller_Shell_2G.create_from_context(context)
        super(self.__class__, self).initialize(context, logger, service)
        self.xena = init_xena(ApiType.socket, self.logger, self.user)

    def cleanup(self):
        self.xena.session.release_ports()
        self.xena.session.disconnect()

    def load_config(self, context, xena_configs_folder):

        reservation_ports = get_resources_from_reservation(context,
                                                           'Xena Chassis Shell 2G.GenericTrafficGeneratorPort')
        for reserved_port in reservation_ports:
            config = get_family_attribute(context, reserved_port.Name, 'Logical Name').strip()
            address = get_address(reserved_port)
            self.logger.debug('Configuration {} will be loaded on Physical location {}'.format(config, address))
            tcp_port = get_family_attribute(context, reserved_port.Name.split('/')[0], 'Controller TCP Port')
            if not tcp_port:
                tcp_port = '22611'
            ip, module, port = address.split('/')
            chassis = self.xena.session.add_chassis(ip, int(tcp_port), self.password)
            xena_port = XenaPort(chassis, '{}/{}'.format(module, port))
            xena_port.reserve(force=True)
            xena_port.load_config(path.join(xena_configs_folder, config.replace('.xpc', '')) + '.xpc')

        self.logger.info("Port Reservation Completed")

    def start_traffic(self, context, blocking):
        self.xena.session.clear_stats()
        self.xena.session.start_traffic(is_blocking(blocking))

    def stop_traffic(self):
        self.xena.session.stop_traffic()

    def get_statistics(self, context, view_name, output_type):

        stats_obj = view_name_2_object[view_name.lower()](self.xena.session)
        stats_obj.read_stats()
        if output_type.lower().strip() == 'json':
            statistics_str = json.dumps(stats_obj.get_flat_stats(), indent=4, sort_keys=True, ensure_ascii=False)
            return json.loads(statistics_str)
        elif output_type.lower().strip() == 'csv':
            output = io.BytesIO()
            captions = [view_name] + stats_obj.get_flat_stats().values()[0].keys()
            writer = csv.DictWriter(output, captions)
            writer.writeheader()
            for obj_name in stats_obj.get_flat_stats():
                d = {view_name: obj_name}
                d.update((stats_obj.get_flat_stats()[obj_name]))
                writer.writerow(d)
            attach_stats_csv(context, self.logger, view_name, output.getvalue().strip())
            return output.getvalue().strip()
        else:
            raise Exception('Output type should be CSV/JSON - got "{}"'.format(output_type))


view_name_2_object = {'port': XenaPortsStats,
                      'stream': XenaStreamsStats,
                      'tpld': XenaTpldsStats}
