from typing import Any

from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnExperimentProtocol, ElnEntryStep

from sapio.enum.tags import ExperimentEntryTags
from sapio.manager.manager_retrievals import Manager
from sapio.model.data_type_models import SampleModel, C_TestAliquotModel
from sapio.webhook.test_aliquot.test_aliquot_creator import TestAliquotCreator


class AddTestAliquotFromSampleTable(CommonsWebhookHandler):

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        samples = Manager.record_model_instance_manager(context).add_existing_records_of_type(
            context.data_record_list, SampleModel
        )

        phase_step = (
            self.get_phase_step(ElnEntryStep(ElnExperimentProtocol(context.eln_experiment, context.user), context.experiment_entry))
            if context.experiment_entry else ""
        )

        test_aliquots = self.create_test_aliquots_for_samples(samples, phase_step)

        if context.experiment_entry:
            test_aliquot_entry = self.get_test_aliquot_entry(phase_step, context)
            if test_aliquot_entry:
                self.exp_handler.add_step_records(test_aliquot_entry, test_aliquots)

        return SapioWebhookResult(True, f"Successfully added {len(test_aliquots)} aliquots.")

    def create_test_aliquots_for_samples(self, samples: list[SampleModel], phase_step: str) -> list[C_TestAliquotModel]:

        # Prepare our utility.
        creator: TestAliquotCreator = TestAliquotCreator(self.context)

        # Prompt the user for the number of aliquots to create.
        number_of_aliquots_to_create = creator.prompt_for_number_of_aliquots_to_create()
        default_values_per_sample: list[dict[str, Any]] = []
        highest_aliquot_numbers_per_sample: list[int] = []

        for sample in samples:
            # Identify the highest aliquot number for the current sample.
            highest_aliquot_number = creator.get_highest_aliquot_number(sample)
            highest_aliquot_numbers_per_sample.append(highest_aliquot_number)

            default_values = dict()
            default_values[C_TestAliquotModel.C_SAMPLETYPE__FIELD_NAME.field_name] = sample.get_ExemplarSampleType_field()
            default_values[C_TestAliquotModel.C_ESTIMATEDCONCENTRATION__FIELD_NAME.field_name] = sample.get_Concentration_field()
            default_values_per_sample.append(default_values)

        # Run the prompt.
        result_values = creator.prompt_user_with_aliquot_details(
            highest_aliquot_numbers_per_sample,
            number_of_aliquots_to_create,
            samples,
            default_values_per_sample
        )

        for row in result_values:
            row[C_TestAliquotModel.C_PHASESTEP__FIELD_NAME.field_name] = phase_step

        # Create the test aliquots, add them to the sample, and display a success message.
        test_aliquots = self.rec_handler.add_models_with_data(C_TestAliquotModel, result_values)
        test_aliquots_by_sample_id = self.group_records_by_sample_id(test_aliquots)

        for sample in samples:
            test_aliquots_for_sample = test_aliquots_by_sample_id.get(sample.get_SampleId_field())
            sample.add_children(test_aliquots_for_sample)

        self.rec_man.store_and_commit()

        return test_aliquots

    def get_test_aliquot_entry(self, phase_step: str, context: SapioWebhookContext) -> ElnEntryStep | None:
        tab_id: int = context.experiment_entry.notebook_experiment_tab_id
        tagged_entries = self.exp_handler.get_steps_by_option(ExperimentEntryTags.TEST_ALIQUOTS, phase_step)

        if len(tagged_entries) <= 0:
            return None

        # Only return an entry if it is in the same tab as the user
        for entry in tagged_entries:
            if entry.eln_entry.notebook_experiment_tab_id == tab_id:
                return entry

        return None

    def get_phase_step(self, samples_entry: ElnEntryStep) -> str:
        options: dict[str, str] = samples_entry.get_options()
        return options.get(ExperimentEntryTags.PHASE_STEP)

    def group_records_by_sample_id(self, test_aliquots: list[C_TestAliquotModel]) -> dict[str, list[C_TestAliquotModel]]:
        """
        Groups experiment records by the SAMPLE_ID field.

        :param test_aliquots: List of experiment records.
        :return: Dictionary grouping records by SAMPLE_ID.
        """
        grouped_records: dict[str, list[C_TestAliquotModel]] = {}

        for record in test_aliquots:
            sample_id = record.get_C_SampleId_field()

            if sample_id not in grouped_records:
                grouped_records[sample_id] = []

            grouped_records[sample_id].append(record)

        return grouped_records