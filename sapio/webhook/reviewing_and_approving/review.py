from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.general.exceptions import SapioUserCancelledException
from sapiopycommons.general.time_util import TimeUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.eln.SapioELNEnums import ElnExperimentStatus
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.enum.tags import ExperimentEntryTags
from sapio.enum.pick_list import ReviewStatuses
from sapio.model.data_type_models import ELNExperimentModel
from sapio.model.eln_classes import ELNExperiment


class MarkReadyForReview(CommonsWebhookHandler):
    """
    This webhook is intended to be invoked when the complete experiment button had changed the status of an experiment
    to 'completed'. The webhook will
        - Move the experiment back to 'new'
        - Make the 'experiment overview' entry visible
        - Set the 'Review Status' on the experiment overview to 'Ready for Review'
        - Set the Experiment Option on the experiment to hide the complete experiment tag.

    Requirement Documentation: https://onetakeda.atlassian.net/browse/ELNMSLAB-540
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        experiment_handler: ExperimentHandler = ExperimentHandler(context)

        # Move the experiment back to 'New'
        experiment_handler.update_experiment(experiment_status=ElnExperimentStatus.New)

        # Make the experiment overview entry visible
        overview_step = experiment_handler.get_step_by_option(ExperimentEntryTags.EXPERIMENT_OVERVIEW)
        experiment_handler.update_step(overview_step, is_hidden=False)

        # Set the review status to ready
        experiment_model: ELNExperimentModel = experiment_handler.get_experiment_model(ELNExperimentModel)
        experiment_model.set_field_value(ELNExperiment.REVIEW_STATUS, ReviewStatuses.READY_FOR_REVIEW)
        self.rec_man.store_and_commit()

        # Hide the complete experiment button
        current_options = experiment_handler.get_experiment_options()
        current_options.update({"HIDE COMPLETE WORKFLOW BUTTON": ""})
        experiment_handler.update_experiment(experiment_option_map=current_options)

        # All done!
        return SapioWebhookResult(True)


class UnlockExperiment(CommonsWebhookHandler):
    """ This webhook is intended to be invoked when the user wants to unlock an experiment. This webhook will:
        - Move the experiment back to 'New'
        - Set the review status to 'Ready for Review'
        - Remove all existing tags so the complete experiment button shows up again

        Requirement Documentation: https://onetakeda.atlassian.net/browse/ELNMSLAB-770
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        experiment_handler: ExperimentHandler = ExperimentHandler(context)

        # Move the experiment back to 'New'
        experiment_handler.update_experiment(experiment_status=ElnExperimentStatus.New)

        # Set the review status to 'Open'
        experiment_model: ELNExperimentModel = experiment_handler.get_experiment_model(ELNExperimentModel)
        experiment_model.set_field_value(ELNExperiment.REVIEW_STATUS, ReviewStatuses.OPEN)
        self.rec_man.store_and_commit()

        # Remove all existing tags so the complete experiment button shows up again
        current_options = {}
        experiment_handler.update_experiment(experiment_option_map=current_options)

        # All done!
        return SapioWebhookResult(True, refresh_notebook_experiment=True)


class PreventAuthorEdit(CommonsWebhookHandler):
    """
    If the current user matches the user who completed the experiment, return a plugin result of false to cancel the
    transaction.
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        exp = ExperimentHandler(context).get_experiment_model(ELNExperimentModel)
        author: str = exp.get_VeloxCompletedBy_field()
        if author == context.user.username:
            return SapioWebhookResult(False, "As the Author of the experiment, you may not update review details.")
        return SapioWebhookResult(True)

class ShowCompleteExperimentButton(CommonsWebhookHandler):
    """ This webhook is intended to be invoked when the user wants to show the complete experiment button. This webhook will:
        - Remove all existing tags so the complete experiment button shows up again

        Requirement Documentation: https://onetakeda.atlassian.net/browse/ELNMSLAB-768
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        experiment_handler: ExperimentHandler = ExperimentHandler(context)
        current_options = {}
        experiment_handler.update_experiment(experiment_option_map=current_options)
        return SapioWebhookResult(True, refresh_notebook_experiment=True)

class CompleteApprovedExperiment(CommonsWebhookHandler):
    """
    This webhook is intended to be triggered when submitting the experiment overview entry. On submission, check that
    the review status is correct and confirm that the user would like to complete. Then complete the experiment.

    Requirement Documentation: https://onetakeda.atlassian.net/browse/ELNMSLAB-543
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        experiment_handler = ExperimentHandler(context)
        eln_model = experiment_handler.get_experiment_model(ELNExperimentModel)

        # Validate the review status
        review_status = eln_model.get_field_value(ELNExperiment.REVIEW_STATUS)
        # TODO: What about rejected? should that cancel?
        if review_status != ReviewStatuses.APPROVED and review_status != ReviewStatuses.REJECTED:
            return SapioWebhookResult(False, "Unable to complete Review, experiment had been neither accepted nor rejected.")

        # Prompt for confirmation to complete.
        user_chose_to_proceed = CallbackUtil(context).yes_no_dialog("The experiment will be marked as completed and locked.", "Would you like to continue?", False)
        if not user_chose_to_proceed:
            raise SapioUserCancelledException()

        # Mark the experiment as completed then
        experiment_handler.update_experiment(experiment_status=ElnExperimentStatus.Completed)

        # All done
        return SapioWebhookResult(True)