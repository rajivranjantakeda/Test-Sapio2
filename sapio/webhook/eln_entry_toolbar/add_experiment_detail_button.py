from typing import List

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.eln.ExperimentEntry import ExperimentEntry
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnExperimentProtocol, ElnEntryStep

from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import ELNExperimentDetailModel


def set_phase_step_on_eln_details(eln_details: list[ELNExperimentDetailModel], eln_step: ElnEntryStep):

    options: dict[str, str] = eln_step.get_options()
    phase_step: str = options.get(ExperimentEntryTags.PHASE_STEP)

    if not phase_step:
        return

    for record in eln_details:
        record.set_field_value("PhaseStep", phase_step)

    pass


class AddExperimentDetailButton(CommonsWebhookHandler):
    """
    This webhook is used for replicating addition of an experiment detail record available out of box, but with the
    additional logic of:
        - Set the PhaseStep field if a tag exists on the entry defining this value
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Prompt the user with an integer input for number of dilutions.
        callback: CallbackUtil = CallbackUtil(context)
        callback.set_dialog_width(width_percent=5)

        number_to_add = callback.integer_input_dialog("Enter The Number of Rows To Add",
                                                            "Enter the number of rows to add to this table entry.",
                                                            "RowCount",
                                                            1,
                                                            0)

        if number_to_add is None or number_to_add <= 0:
            return SapioWebhookResult(True)

        eln_protocol: ElnExperimentProtocol = ElnExperimentProtocol(context.eln_experiment, context.user)
        eln_step: ElnEntryStep = ElnEntryStep(eln_protocol, context.experiment_entry)

        eln_details: list[ELNExperimentDetailModel] = self.create_experiment_details(number_to_add, eln_step)

        field_names = self.get_field_names_for_entry()

        if "PhaseStep" in field_names:
            set_phase_step_on_eln_details(eln_details, eln_step)

        self.rec_man.store_and_commit()

        return SapioWebhookResult(True)

    def create_experiment_details(self, number_to_add: int, eln_step: ElnEntryStep) -> list[ELNExperimentDetailModel]:

        eln_details: list[ELNExperimentDetailModel] = self.exp_handler.add_eln_rows(eln_step, number_to_add, ELNExperimentDetailModel)

        experiment = self.inst_man.add_existing_record(self.exp_handler.get_experiment_record())
        experiment.add_children(eln_details)

        return eln_details

    def get_field_names_for_entry(self) -> list[str]:

        notebook_id: int = self.context.eln_experiment.notebook_experiment_id
        entry_id: int = self.context.experiment_entry.entry_id
        entry_with_defs: ExperimentEntry = self.context.eln_manager.get_experiment_entry(
            eln_experiment_id=notebook_id,
            entry_id=entry_id,
            to_retrieve_field_definitions=True
        )

        if not hasattr(entry_with_defs, "field_definition_list"):
            return list()

        field_defs: list[AbstractVeloxFieldDefinition] = entry_with_defs.field_definition_list
        field_names: list[str] = list()

        for field_def in field_defs:
            field_names.append(field_def.data_field_name)

        return field_names