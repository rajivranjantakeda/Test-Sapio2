from typing import List, Dict

from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.eln.SapioELNEnums import TemplateAccessLevel
from sapiopylib.rest.pojo.eln.protocol_template import ProtocolTemplateQuery, ProtocolTemplateInfo
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.webhook.grabber.grabber import get_tagged_protocols_by_display_name


class PurificationBuildingBlockSelectionList(CommonsWebhookHandler):
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # TODO: Consolidate source contstant with the one in the purification grabber webhook.
        protocols: List[ProtocolTemplateInfo] = context.eln_manager.get_protocol_template_info_list(ProtocolTemplateQuery(whitelist_access_levels=[TemplateAccessLevel.PUBLIC]))
        purification_blocks: Dict[str, ProtocolTemplateInfo] = get_tagged_protocols_by_display_name(protocols, "Purification")
        return SapioWebhookResult(True, list_values=[display_name for display_name in purification_blocks.keys()])