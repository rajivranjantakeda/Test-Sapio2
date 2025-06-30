from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.ELNService import ElnManager
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep

class DeleteExperimentTabAndEntries(CommonsWebhookHandler):
    """A webhook handler class to delete the last tab and its entries from an experiment in the ELN system."""

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        eln_manager: ElnManager = ElnManager(context.user)

        # Get the experiment id.
        exp_id = context.eln_experiment.notebook_experiment_id

        # Get the Experiment Tabs.
        experiment_tabs = eln_manager.get_tabs_for_experiment(exp_id)

        if len(experiment_tabs) <= 1:
            return SapioWebhookResult(False, "This experiment only contains one tab, which cannot be deleted!")

        # Get the last Tab entry.
        last_tab = eln_manager.get_tabs_for_experiment(exp_id)[-1]

        # Prompt the user to ask if they are sure they want to delete the last tab.
        deletetab: bool = CallbackUtil(context).yes_no_dialog("Delete Tab", f"Are you sure you want to delete the tab '{last_tab.tab_name}'?")

        if not deletetab:
            return SapioWebhookResult(True, "Tab deletion cancelled.")

        # Delete the entries from last tab.
        all_steps: list[ElnEntryStep] = self.exp_handler.get_all_steps()
        last_entry_step_ids: list[int] = [step.get_id() for step in all_steps if step.eln_entry.notebook_experiment_tab_id == last_tab.tab_id]
        eln_manager.delete_experiment_entry_list(exp_id, last_entry_step_ids)

        # Delete the tab.
        eln_manager.delete_tab_for_experiment(exp_id, last_tab.tab_id)

        return SapioWebhookResult(True, "Success!")