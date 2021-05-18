"""
Xena controller driver.
"""
from cloudshell.traffic.tg import TgControllerDriver

from xena_handler import XenaHandler


class XenaController2GDriver(TgControllerDriver):
    """Xena controller shell API, no business logic."""

    def __init__(self):
        self.handler = XenaHandler()

    def load_config(self, context, config_file_location):
        """Reserve ports and load Xena configuration files from the given directory."""
        return super().load_config(context, config_file_location)

    def start_traffic(self, context, blocking):
        """Start traffic on all ports."""
        return super().start_traffic(context, blocking)

    def stop_traffic(self, context):
        """Stop traffic on all ports."""
        return super().stop_traffic(context)

    def get_statistics(self, context, view_name, output_type):
        """Get view statistics.

        :param view_name: port, traffic item, flow group etc.
        :param output_type: CSV or JSON.
        """
        return super().get_statistics(context, view_name, output_type)

    #
    # Parent commands are not visible so we re define them in child.
    #

    def initialize(self, context):
        super().initialize(context)

    def cleanup(self):
        super().cleanup()

    def keep_alive(self, context, cancellation_context):
        super().keep_alive(context, cancellation_context)
