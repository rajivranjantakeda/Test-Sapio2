from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult


class ReturnPopupResultFalse(CommonsWebhookHandler):

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        CallbackUtil(context).display_error("This is an error")
        return SapioWebhookResult(False)