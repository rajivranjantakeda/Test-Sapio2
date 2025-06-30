from typing import List

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.customreport.custom_report_builder import CustomReportBuilder
from sapiopycommons.customreport.term_builder import TermBuilder
from sapiopycommons.general.exceptions import SapioCriticalErrorException, SapioUserErrorException
from sapiopycommons.general.time_util import TimeUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.DataTypeService import DataTypeManager
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookEnums import SearchType
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.recordmodel.RecordModelUtil import RecordModelUtil
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import RecordModelWrapperUtil

from sapio.enum.tags import ExperimentEntryTags
from sapio.manager.manager_retrievals import Manager
from sapio.model.data_type_models import C_TestAliquotModel, SampleModel, ELNExperimentModel, ELNExperimentDetailModel
from sapio.model.eln_classes import ELNExperiment, ELNExperimentDetail
from sapio.util.datatype_util import DataTypeUtil
from sapio.webhook.test_aliquot.designation import DesignationManager
from sapio.webhook.test_aliquot.launch_test_aliquots import TestAliquotHandler, TestAliquotValidator


class AddTestAliquotsToExperiment(CommonsWebhookHandler):
    """
    This class exists for bringing in existing test aliquots to a current experiment. This button will exist on the
    entry toolbar for applicable experiments. The test aliquots will be converted into aliquot samples,
    and brought into the experiment.
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Do nothing if there is no client callback available.
        # TODO: The rule invocation should really check if the experiment is new and not invoke this if it is.
        if not self.can_send_client_callback():
            return SapioWebhookResult(True)

        # Create a custom report where "Status" is "Ready" and "Designation" is equal to the current templates'
        # designation.
        builder = CustomReportBuilder(C_TestAliquotModel)

        # Get the designation required based on the current template.
        designation_manager: DesignationManager = DesignationManager(context)
        designation: str | None = designation_manager.get_designation(context.eln_experiment.template_id)
        if designation is None:
            return SapioWebhookResult(True, "No designation found for this experiment template. "
                                            + "Please contact a system administrator.")

        # Ensure we have valid test aliquots for this experiments designation.
        designation_term = TermBuilder.is_term(builder.data_type_name, C_TestAliquotModel.C_DESIGNATION__FIELD_NAME, designation)
        status_term = TermBuilder.is_term(builder.data_type_name, C_TestAliquotModel.C_STATUS__FIELD_NAME, "Ready")

        # Ensure that the aliquots don't exist in the experiment already.
        existing_aliquots = self.get_existing_aliquots()
        existing_sample_ids = RecordModelUtil.get_value_list(RecordModelWrapperUtil.unwrap_list(existing_aliquots), C_TestAliquotModel.C_SAMPLEID__FIELD_NAME.field_name)
        valid_source_sample = TermBuilder.not_term(builder.data_type_name, C_TestAliquotModel.C_SAMPLEID__FIELD_NAME, existing_sample_ids)

        # Ensure that the assay matches the existing assay value.
        assay_details_step = self.exp_handler.get_step_by_option(ExperimentEntryTags.ASSAY_DETAILS)
        if assay_details_step is None:
            raise SapioUserErrorException("No assay details step found in the experiment.")
        detail: ELNExperimentDetailModel = self.exp_handler.get_step_models(assay_details_step, ELNExperimentDetailModel).pop()
        # TODO: Use a constant when record models have predefined fields.
        assay: str = detail.get_field_value("C_Assay")
        valid_assay = TermBuilder.is_term(builder.data_type_name, C_TestAliquotModel.C_ASSAY__FIELD_NAME, assay)

        # Combine terms. Only add terms for existing aliquots if there are any.
        root_term = TermBuilder.and_terms(designation_term, status_term)
        if existing_aliquots:
            root_term = TermBuilder.and_terms(root_term, valid_source_sample)

        if assay:
            root_term = TermBuilder.and_terms(root_term, valid_assay)

        # Complete the report.
        builder.set_root_term(root_term)

        for field_def in DataTypeUtil.get_field_definitions_in_order(C_TestAliquotModel.DATA_TYPE_NAME, context):
            builder.add_column(
                field=field_def.data_field_name,
                field_type=field_def.data_field_type,
                data_type=field_def.data_type_name
            )

        report_criteria = builder.build_report_criteria()

        # Prompt based on that.
        aliquots_chosen: List[C_TestAliquotModel] = CallbackUtil(context).input_selection_dialog(
            wrapper_type=C_TestAliquotModel,
            only_key_fields=True,
            msg="Please select some test aliquots to bring in.",
            search_types=[
                SearchType.ADVANCED_SEARCH,
                SearchType.QUICK_SEARCH,
                SearchType.BROWSE_TREE
            ],
            custom_search=report_criteria
        )

        # Initialize the HPLC Handler.
        handler = TestAliquotHandler(context, context.eln_experiment)

        # Get the collection of all test aliquots for the experiment: new and old.
        all_aliquots = list(existing_aliquots)
        all_aliquots.extend(aliquots_chosen)

        # Update experiment details individually.
        handler.set_product(all_aliquots, detail)
        handler.set_submitter(all_aliquots, detail)
        if not assay:
            handler.set_assay(aliquots_chosen, detail)

        # Update experiment parent.
        handler.add_experiment_to_sample_studies(all_aliquots)

        # Create the samples.
        new_samples = handler.convert_test_aliquots_to_samples(aliquots_chosen)
        handler.add_samples(new_samples)

        # All done.
        return SapioWebhookResult(True)

    def get_existing_aliquots(self) -> List[C_TestAliquotModel]:
        # Load the existing samples, and get the test aliquots from them.
        existing_samples = self.exp_handler.get_step_models("Samples", SampleModel)
        self.rel_man.load_reverse_side_links_of_type(existing_samples, C_TestAliquotModel,
                                                                       C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name)
        existing_test_aliquots: List = list()
        for sample in existing_samples:
            test_aliquot = sample.get_reverse_side_link(C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name, C_TestAliquotModel)
            existing_test_aliquots.extend(test_aliquot)

        return existing_test_aliquots
