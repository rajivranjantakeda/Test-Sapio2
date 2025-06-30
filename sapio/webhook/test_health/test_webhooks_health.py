from sapiopycommons.general.popup_util import PopupUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.info.build_info import BuildInfo


class TestWebhookServerConnection(CommonsWebhookHandler):
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        if context.client_callback_result is not None:
            return SapioWebhookResult(True)

        build_info = BuildInfo.print_info()
        message = "<b>Connecting user:</b>\n" + context.user.username + "\n\n<b>Webhook build info:</b>\n" + build_info

        return PopupUtil.display_ok_popup("Webhook Successfully Executed", message)
