from typing import List

from sapiopycommons.general.exceptions import SapioException, SapioUserErrorException
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import ELNSampleDetailModel, SampleModel, C_TestAliquotModel
from sapio.model.eln_classes import ELNSampleDetail
from sapio.webhook.test_aliquot.add_test_aliquot_action_button import TestAliquotCreator


class AddTestAliquotsFromSampleDetail(CommonsWebhookHandler):
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Prepare our utility.
        creator: TestAliquotCreator = TestAliquotCreator(context)

        # Get the sample detail, and it's source sample.
        detail_model: ELNSampleDetailModel = self.get_sample_detail()
        sample: SampleModel = self.get_source_sample(detail_model)

        # Prompt the user for the number of aliquots to create.
        number_of_aliquots_to_create = creator.prompt_for_number_of_aliquots_to_create()

        # Identify the highest aliquot number for the current sample.
        highest_aliquot_number = creator.get_highest_aliquot_number(sample)

        # Compile the details for the prompt. Some values should be overriden no matter what, and some values should
        # be defaults.
        sample_type = detail_model.get_field_value(ELNSampleDetail.SAMPLE_TYPE_2)

        concentration_fields = ["Concentration", "ConcA280A320Calc"]
        default_concentration = self.get_first_non_null_value(detail_model, concentration_fields)

        default_values = dict()
        default_values[C_TestAliquotModel.C_SAMPLETYPE__FIELD_NAME.field_name] = sample_type
        default_values[C_TestAliquotModel.C_ESTIMATEDCONCENTRATION__FIELD_NAME.field_name] = default_concentration
        override_fields = dict()
        override_fields[C_TestAliquotModel.C_SAMPLETYPE__FIELD_NAME.field_name] = sample_type

        # Run the prompt.
        result_values = creator.prompt_user_with_aliquot_details(
            [highest_aliquot_number],
            number_of_aliquots_to_create,
            [sample],
            [override_fields],
            default_values
        )

        # Overwrite the sample type from the source sample with the sample details sample type.
        phase_step = detail_model.get_field_value(ELNSampleDetail.PHASE_STEP)
        for row in result_values:
            row[C_TestAliquotModel.C_SAMPLETYPE__FIELD_NAME.field_name] = sample_type
            row[C_TestAliquotModel.C_PHASESTEP__FIELD_NAME.field_name] = phase_step

        # Create the test aliquots, add them to the sample, and display a success message.
        test_aliquots = self.rec_handler.add_models_with_data(C_TestAliquotModel, result_values)
        sample.add_children(test_aliquots)
        self.rec_man.store_and_commit()

        # Add them to the tagged entry, if found.
        tagged_entries = self.exp_handler.get_steps_by_option(ExperimentEntryTags.TEST_ALIQUOTS, phase_step)
        if len(tagged_entries) > 0:
            self.exp_handler.add_step_records(tagged_entries.pop(), test_aliquots)

        # Return a success message.
        success_message: str = ("Successfully added " + str(number_of_aliquots_to_create) + " aliquots under sample " +
                                sample.get_SampleId_field())
        return SapioWebhookResult(True, success_message)

    def get_first_non_null_value(self, detail_model, field_names):
        """
        Iterates through a list of field names and returns the first non-null value.
        """
        for field in field_names:
            value = detail_model.get_field_value(field)
            if value is not None:
                return value
        return None  # Return None if no fields have a value

    def get_source_sample(self, detail_model: ELNSampleDetailModel) -> SampleModel:
        """
        Enforce that a single record is present in the context, and that it is a Sample Detail.
        Then get the source sample.
        """
        # Get the sample record.
        sample_id = detail_model.get_SampleId_field()
        matched_records: List[SampleModel] = self.rec_handler.query_models(SampleModel, SampleModel.SAMPLEID__FIELD_NAME,
                                                                           [sample_id])
        if len(matched_records) < 1:
            raise SapioException("Could not find the sample record for this Sample Detail with sample ID '" + sample_id + "'.")
        if len(matched_records) > 1:
            raise SapioException("Multiple sample records found for this Sample Detail with sample ID '" + sample_id + "'.")
        return matched_records.pop()

    def get_sample_detail(self):
        """ Get the sample detail record from the context, or raise an exception. """
        if len(self.context.data_record_list) > 1:
            raise SapioUserErrorException("Please select only one record.")
        if len(self.context.data_record_list) < 1:
            raise SapioUserErrorException("Please select a record.")
        if not self.context.data_type_name.startswith(ELNSampleDetailModel.DATA_TYPE_NAME):
            raise SapioUserErrorException("Webhook has been configured incorrectly. "
                                          + "Please contact a system administrator.")
        detail_model = self.inst_man.add_existing_record_of_type(self.context.data_record_list[0], ELNSampleDetailModel)
        return detail_model