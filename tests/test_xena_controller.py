"""
Tests for XenaController2GDriver.
"""
import json
from os import path

import pytest
from _pytest.fixtures import SubRequest
from cloudshell.api.cloudshell_api import AttributeNameValue, CloudShellAPISession, InputNameValue
from cloudshell.shell.core.driver_context import ResourceCommandContext
from cloudshell.traffic.helpers import get_location, get_reservation_id, get_resources_from_reservation, set_family_attribute
from cloudshell.traffic.tg import XENA_CHASSIS_MODEL, XENA_CONTROLLER_MODEL
from shellfoundry_traffic.test_helpers import TestHelpers, create_session_from_config

from src.xena_driver import XenaController2GDriver

ALIAS = "Xena Controller"

ports = ["Xena-117/Module0/Port0", "Xena-117/Module0/Port1"]


@pytest.fixture(params=[("176.22.65.117", "22611")])
def controller(request: SubRequest) -> list:
    return request.param


@pytest.fixture(scope="session")
def session() -> CloudShellAPISession:
    yield create_session_from_config()


@pytest.fixture()
def test_helpers(session: CloudShellAPISession) -> TestHelpers:
    test_helpers = TestHelpers(session)
    test_helpers.create_reservation()
    yield test_helpers
    test_helpers.end_reservation()


@pytest.fixture()
def driver(test_helpers: TestHelpers, controller: list) -> XenaController2GDriver:
    controller_address, controller_port = controller
    attributes = {
        f"{XENA_CONTROLLER_MODEL}.Address": controller_address,
        f"{XENA_CONTROLLER_MODEL}.Controller TCP Port": controller_port,
        f"{XENA_CONTROLLER_MODEL}.User": "xena-controller-shell",
    }
    init_context = test_helpers.service_init_command_context(XENA_CONTROLLER_MODEL, attributes)
    driver = XenaController2GDriver()
    driver.initialize(init_context)
    yield driver
    driver.cleanup()


@pytest.fixture()
def context(session: CloudShellAPISession, test_helpers: TestHelpers, controller: list) -> ResourceCommandContext:
    controller_address, controller_port = controller
    attributes = [
        AttributeNameValue(f"{XENA_CONTROLLER_MODEL}.Address", controller_address),
        AttributeNameValue(f"{XENA_CONTROLLER_MODEL}.Controller TCP Port", controller_port),
        AttributeNameValue(f"{XENA_CONTROLLER_MODEL}.User", "xena-controller-shell"),
    ]
    session.AddServiceToReservation(test_helpers.reservation_id, XENA_CONTROLLER_MODEL, ALIAS, attributes)
    context = test_helpers.resource_command_context(service_name=ALIAS)
    session.AddResourcesToReservation(test_helpers.reservation_id, ports)
    reservation_ports = get_resources_from_reservation(context, f"{XENA_CHASSIS_MODEL}.GenericTrafficGeneratorPort")
    set_family_attribute(context, reservation_ports[0].Name, "Logical Name", "test_config.xpc")
    set_family_attribute(context, reservation_ports[1].Name, "Logical Name", "test_config.xpc")
    yield context


class TestXenaController2GDriverDriver:
    """Test direct driver calls."""

    def test_load_config(self, driver: XenaController2GDriver, context: ResourceCommandContext) -> None:
        driver.load_config(context, path.dirname(__file__))

    def test_run_traffic(self, driver, context):
        driver.load_config(context, path.dirname(__file__))
        reservation_ports = get_resources_from_reservation(context, f"{XENA_CHASSIS_MODEL}.GenericTrafficGeneratorPort")
        port_name = get_location(reservation_ports[0])

        driver.start_traffic(context, "True")
        port_stats = driver.get_statistics(context, "Port", "JSON")
        assert int(port_stats[port_name]["pt_total_packets"]) == 16000
        stream_stats = driver.get_statistics(context, "Stream", "JSON")
        assert int(stream_stats["Stream 1-1"]["packets"]) == 8000
        tpld_stats = driver.get_statistics(context, "TPLD", "JSON")
        tpld_name = get_location(reservation_ports[0])[-3:] + "/0"
        assert int(tpld_stats[tpld_name]["pr_tpldtraffic_pac"]) == 8000

        driver.start_traffic(context, "False")
        stats = driver.get_statistics(context, "Port", "JSON")
        assert int(stats[get_location(reservation_ports[0])]["pt_total_packets"]) < 16000
        driver.stop_traffic(context)


class TestIxNetworkControllerShell:
    """Test indirect Shell calls."""

    def test_load_config(self, session: CloudShellAPISession, context: ResourceCommandContext) -> None:
        cmd_inputs = [InputNameValue("config_file_location", path.dirname(__file__))]
        session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "load_config", cmd_inputs)

    def test_run_traffic(self, session: CloudShellAPISession, context: ResourceCommandContext):
        cmd_inputs = [InputNameValue("config_file_location", path.dirname(__file__))]
        session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "load_config", cmd_inputs)
        reservation_ports = get_resources_from_reservation(context, f"{XENA_CHASSIS_MODEL}.GenericTrafficGeneratorPort")
        port_name = get_location(reservation_ports[0])

        cmd_inputs = [InputNameValue("blocking", "True")]
        session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "start_traffic", cmd_inputs)
        cmd_inputs = [InputNameValue("view_name", "Port"), InputNameValue("output_type", "JSON")]
        port_stats = session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "get_statistics", cmd_inputs)
        assert int(json.loads(port_stats.Output)[port_name]["pt_total_packets"]) == 16000
        cmd_inputs = [InputNameValue("view_name", "Stream"), InputNameValue("output_type", "JSON")]
        stream_stats = session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "get_statistics", cmd_inputs)
        assert int(json.loads(stream_stats.Output)["Stream 1-1"]["packets"]) == 8000

        cmd_inputs = [InputNameValue("view_name", "TPLD"), InputNameValue("output_type", "JSON")]
        tpld_stats = session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "get_statistics", cmd_inputs)
        tpld_name = get_location(reservation_ports[0])[-3:] + "/0"
        assert int(json.loads(tpld_stats.Output)[tpld_name]["pr_tpldtraffic_pac"]) == 8000

        cmd_inputs = [InputNameValue("blocking", "False")]
        session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "start_traffic", cmd_inputs)
        cmd_inputs = [InputNameValue("view_name", "Port"), InputNameValue("output_type", "JSON")]
        port_stats = session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "get_statistics", cmd_inputs)
        assert int(json.loads(port_stats.Output)[port_name]["pt_total_packets"]) < 16000
        session.ExecuteCommand(get_reservation_id(context), ALIAS, "Service", "stop_traffic")
