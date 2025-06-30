from sapio.webhook.grabber.grabber import ProtocolGrabber
from sapio.webhook.grabber.grabber_context import CustomGrabberContext

class PurificationGrabber(ProtocolGrabber):
    """
    A protocol grabber specifically for bringing protocols tagged for use in the purification workflow.
    """

    def execute_custom_logic(self, context: CustomGrabberContext):
        return

    def get_tag_regex(self):
        return "Purification"
