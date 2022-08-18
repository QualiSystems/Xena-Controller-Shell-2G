"""
Xena controller shell driver API. The business logic is implemented in xena_handler.py.
"""
# pylint: disable=unused-argument
from typing import Union

from cloudshell.shell.core.driver_context import CancellationContext, InitCommandContext, ResourceCommandContext
from cloudshell.traffic.tg import TgControllerDriver, enqueue_keep_alive

from xena_handler import XenaHandler


class XenaController2GDriver(TgControllerDriver):
    """Xena controller shell API, no business logic."""

    def __init__(self) -> None:
        """Initialize object variables, actual initialization is performed in initialize method."""
        super().__init__()
        self.handler = XenaHandler()

    def initialize(self, context: InitCommandContext) -> None:
        """Initialize Xena controller shell (from API)."""
        super().initialize(context)
        self.handler.initialize(context, self.logger)

    def cleanup(self) -> None:
        """Cleanup TestCenter controller shell (from API)."""
        self.handler.cleanup()
        super().cleanup()

    def load_config(self, context: ResourceCommandContext, config_file_location: str) -> None:
        """Load Xena configuration file, map and reserve ports."""
        enqueue_keep_alive(context)
        self.handler.load_config(context, config_file_location)

    def start_traffic(self, context: ResourceCommandContext, blocking: str) -> None:
        """Start traffic on all ports.

        :param blocking: True - return after traffic finish to run, False - return immediately.
        """
        self.handler.start_traffic(blocking)

    def stop_traffic(self, context: ResourceCommandContext) -> None:
        """Stop traffic on all ports."""
        self.handler.stop_traffic()

    def get_statistics(self, context: ResourceCommandContext, view_name: str, output_type: str) -> Union[dict, str]:
        """Get view statistics.

        :param view_name: Statistics view - port, stream or tpld.
        :param output_type: CSV or JSON.
        """
        return self.handler.get_statistics(context, view_name, output_type)

    def run_rfc(self, context: ResourceCommandContext, test: str, config_file_location: str) -> None:
        """Run RFC test.

        :param test: RFC test number.
        :param config_file_location: Full path to RFC test configuration file.
        """
        self.handler.run_rfc(context, test, config_file_location)

    def keep_alive(self, context: ResourceCommandContext, cancellation_context: CancellationContext) -> None:
        """Keep Xena controller shell sessions alive (from TG controller API).

        Parent commands are not visible so we re re-define this method in child.
        """
        super().keep_alive(context, cancellation_context)
