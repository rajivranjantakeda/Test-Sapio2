from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.general.exceptions import SapioUserCancelledException
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.DataRecord import DataRecord
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.model.data_type_models import ELNExperimentModel
from sapio.model.eln_classes import ELNExperiment


class CancellingExperiment(CommonsWebhookHandler):
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Show a pop-up prompting the user to provide a reason for cancelling the experiment.
        callback = CallbackUtil(context)
        user_input: str = ""
        while len(user_input) < 1:
            try:
                # TODO: This dialog should really not be closable.
                user_input = callback.string_input_dialog(
                    title="Cancelling Experiment",
                    msg="Please provide a reason for cancelling the experiment.",
                    field_name="ReasonForCancelling"
                )
            except SapioUserCancelledException as e:
                # Just keep looping, even if the user cancels. We have to have enforce the reason as well as we can.
                continue
        # Get a reference of the current experiment.
        experiment: ELNExperimentModel = ExperimentHandler(context).get_experiment_model(ELNExperimentModel)

        # Set a value for the reason for cancelling.
        experiment.set_field_value(ELNExperiment.REASON_FOR_CANCELLING, user_input)
        experiment.set_field_value(ELNExperiment.REVIEW_STATUS, "Cancelled")

        self.rec_man.store_and_commit()
        return SapioWebhookResult(True, "Success!")
