from sapio.webhook.grabber.grabber import ProtocolGrabber
from sapio.webhook.grabber.grabber_context import CustomGrabberContext

class CellCultureGrabber(ProtocolGrabber):
    """
    This is a custom protocol grabber specific to the Cell Culture grabber.
    """
    def execute_custom_logic(self, grabber_context: CustomGrabberContext):
        pass

    def get_tag_regex(self):
        return "Cell Culture"
