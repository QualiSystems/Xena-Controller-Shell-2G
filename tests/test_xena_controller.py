
from os import path
import time
import pytest
import json

from cloudshell.api.cloudshell_api import AttributeNameValue, InputNameValue
from cloudshell.traffic.common import add_resources_to_reservation, get_reservation_id, get_resources_from_reservation
from cloudshell.traffic.tg_helper import set_family_attribute, get_address
from cloudshell.traffic.tg import XENA_CONTROLLER_MODEL
from shellfoundry.releasetools.test_helper import (create_init_command_context, create_session_from_deployment,
                                                   create_service_command_context, end_reservation)

from src.xena_driver import XenaController2GDriver

ports = ['Valkyrie/Module0/Port0', 'Valkyrie/Module0/Port1']


@pytest.fixture()
def model():
    yield XENA_CONTROLLER_MODEL


@pytest.fixture()
def alias():
    yield 'Xena Controller'


@pytest.fixture()
def chassis():
    yield '176.22.65.117', '22606'


@pytest.fixture()
def session():
    yield create_session_from_deployment()


@pytest.fixture()
def driver(session, model, chassis):
    controller_address, controller_port = chassis
    attributes = {model + '.Address': controller_address,
                  model + '.Controller TCP Port': controller_port,
                  model + '.User': 'xena-controller-shell',
                  model + '.Password': 'h8XUgX3gyjY0vKMg0wQxKg=='}
    init_context = create_init_command_context(session, 'CS_TrafficGeneratorController', model, 'na', attributes,
                                               'Service')
    driver = XenaController2GDriver()
    driver.initialize(init_context)
    print(driver.logger.handlers[0].baseFilename)
    yield driver
    driver.cleanup()


@pytest.fixture()
def context(session, model, alias, chassis):
    controller_address, controller_port = chassis
    attributes = [AttributeNameValue(model + '.Address', controller_address),
                  AttributeNameValue(model + '.Controller TCP Port', controller_port),
                  AttributeNameValue(model + '.User', 'xena-controller-shell'),
                  AttributeNameValue(model + '.Password', 'xena')]
    context = create_service_command_context(session, model, alias, attributes)
    add_resources_to_reservation(context, *ports)
    reservation_ports = get_resources_from_reservation(context, 'Xena Chassis Shell 2G.GenericTrafficGeneratorPort')
    set_family_attribute(context, reservation_ports[0].Name, 'Logical Name', 'test_config.xpc')
    set_family_attribute(context, reservation_ports[1].Name, 'Logical Name', 'test_config.xpc')
    yield context
    end_reservation(session, get_reservation_id(context))


class TestIxNetworkControllerDriver(object):

    def test_load_config(self, driver, context):
        driver.load_config(context, path.dirname(__file__))

    def test_run_traffic(self, driver, context):
        driver.load_config(context, path.dirname(__file__))
        reservation_ports = get_resources_from_reservation(context, 'Xena Chassis Shell 2G.GenericTrafficGeneratorPort')
        port_name = get_address(reservation_ports[0])

        driver.start_traffic(context, 'True')
        port_stats = driver.get_statistics(context, 'Port', 'JSON')
        assert(int(port_stats[port_name]['pt_total_packets']) == 16000)
        stream_stats = driver.get_statistics(context, 'Stream', 'JSON')
        assert(int(stream_stats['Stream 1-1']['packets']) == 8000)
        tpld_stats = driver.get_statistics(context, 'TPLD', 'JSON')
        tpld_name = get_address(reservation_ports[0])[-3:] + '/0'
        assert(int(tpld_stats[tpld_name]['pr_tpldtraffic_pac']) == 8000)

        print(driver.get_statistics(context, 'Port', 'CSV'))
        print(driver.get_statistics(context, 'Stream', 'CSV'))
        print(driver.get_statistics(context, 'TPLD', 'CSV'))

        driver.start_traffic(context, 'False')
        stats = driver.get_statistics(context, 'Port', 'JSON')
        assert(int(stats[get_address(reservation_ports[0])]['pt_total_packets']) < 16000)
        driver.stop_traffic(context)


class TestIxNetworkControllerShell(object):

    def test_load_config(self, session, context, alias):
        session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                               'load_config',
                               [InputNameValue('config_file_location', path.dirname(__file__))])

    def test_run_traffic(self, session, context, alias):
        session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                               'load_config',
                               [InputNameValue('config_file_location', path.dirname(__file__))])
        reservation_ports = get_resources_from_reservation(context, 'Xena Chassis Shell 2G.GenericTrafficGeneratorPort')
        port_name = get_address(reservation_ports[0])

        session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                               'start_traffic',
                               [InputNameValue('blocking', 'True')])
        port_stats = session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                                            'get_statistics',
                                            [InputNameValue('view_name', 'Port'),
                                             InputNameValue('output_type', 'JSON')])
        assert(int(json.loads(port_stats.Output)[port_name]['pt_total_packets']) == 16000)
        stream_stats = session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                                            'get_statistics',
                                            [InputNameValue('view_name', 'Stream'),
                                             InputNameValue('output_type', 'JSON')])
        assert(int(json.loads(stream_stats.Output)['Stream 1-1']['packets']) == 8000)

        tpld_stats = session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                                            'get_statistics',
                                            [InputNameValue('view_name', 'TPLD'),
                                             InputNameValue('output_type', 'JSON')])
        tpld_name = get_address(reservation_ports[0])[-3:] + '/0'
        assert(int(json.loads(tpld_stats.Output)[tpld_name]['pr_tpldtraffic_pac']) == 8000)

        session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                               'start_traffic',
                               [InputNameValue('blocking', 'False')])
        port_stats = session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                                            'get_statistics',
                                            [InputNameValue('view_name', 'Port'),
                                             InputNameValue('output_type', 'JSON')])
        assert(int(json.loads(port_stats.Output)[port_name]['pt_total_packets']) < 16000)
        session.ExecuteCommand(get_reservation_id(context), alias, 'Service',
                               'stop_traffic')
