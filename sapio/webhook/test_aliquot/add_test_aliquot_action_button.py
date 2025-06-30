from typing import List

from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.model.data_type_models import SampleModel, C_TestAliquotModel
from sapio.webhook.test_aliquot.test_aliquot_creator import TestAliquotCreator


class AddTestAliquotsButton(CommonsWebhookHandler):
    """
    This webhook corresponds to the 'Add Test Aliquots' Action Button field on the sample data type. The intention is
    to prompt the user for details about the Test Aliquots to create, and add them under sample record this button
    is invoked from.

    Documentation Reference: https://onetakeda.atlassian.net/browse/ELNMSLAB-497
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        test_aliquot_creator = TestAliquotCreator(context)
        # 1. Prompt the user for the number of test aliquots to create.
        number_of_aliquots_to_create = test_aliquot_creator.prompt_for_number_of_aliquots_to_create()

        # 2. Identify the largest aliquot number for the current sample.
        sample: SampleModel = self.inst_man.add_existing_record_of_type(context.data_record, SampleModel)
        highest_aliquot_number = test_aliquot_creator.get_highest_aliquot_number(sample)

        # 3. Display a table popup with a new row per new test aliquot with all fields except for the system fields.
        result_values = test_aliquot_creator.prompt_user_with_aliquot_details([highest_aliquot_number],
                                                                              number_of_aliquots_to_create,
                                                                              [sample])

        # 4. Create the test aliquots, add them to the sample, display a success message.
        test_aliquots: List[C_TestAliquotModel] = RecordHandler(context).add_models_with_data(C_TestAliquotModel,
                                                                                              result_values)
        sample.add_children(test_aliquots)
        self.rec_man.store_and_commit()
        success_message: str = ("Successfully added " + str(number_of_aliquots_to_create) + " aliquots under sample " +
                                sample.get_SampleId_field())

        return SapioWebhookResult(True, display_text=success_message)






