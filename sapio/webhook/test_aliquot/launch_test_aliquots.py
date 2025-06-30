from typing import List, Set, Dict

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.general.exceptions import SapioUserCancelledException, SapioUserErrorException
from sapiopycommons.general.time_util import TimeUtil
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.eln.ElnExperiment import ElnExperiment, TemplateExperimentQueryPojo, ElnTemplate, \
    InitializeNotebookExperimentPojo
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookDirective import ElnExperimentDirective
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep
from sapiopylib.rest.utils.recordmodel.RecordModelUtil import RecordModelUtil
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import RecordModelWrapperUtil
from sapiopylib.rest.utils.recordmodel.RelationshipPath import RelationshipPath
from sapiopylib.rest.utils.recordmodel.properties import Parent, Child

from sapio.enum.tags import ExperimentEntryTags
from sapio.manager.manager_retrievals import Manager
from sapio.model.data_type_models import C_TestAliquotModel, SampleModel, StudyModel, ELNExperimentModel, \
    ELNExperimentDetailModel, NotebookDirectoryModel
from sapio.model.eln_classes import ELNExperimentDetail, ELNSampleDetail
from sapio.webhook.test_aliquot.designation import DesignationManager


class TestAliquotValidator:
    """
    This is a utility class that is used to validate the selected test aliquots for the Test Aliquot designation
    experiments.
    The validator will hold the logic for
        1. Checking for hard errors. If a hard error is encountered, a user exception will be raised to cancel the webhook
        2. Checking for warnings. If a warning is encountered, the user will be prompted to continue or cancel the webhook
        3. Filtering the list of test aliquots to only include those that are valid for the experiment.
    """
    callback: CallbackUtil

    def __init__(self, context: SapioWebhookContext):
        """
        We need the callback, so that we can prompt the user when there are warnings.
        """
        self.callback = CallbackUtil(context)

    def check_for_hard_errors(self, aliquot_instructions):
        """
        Checks for hard errors in the selected test aliquots. The following conditions are checked:
        - Some of the selected test aliquots must have a Designation other than "Storage".
        - Of those, some of the test aliquots must have a status of "Ready".
        - Of those, all test aliquots must have a unique source sample and have the same assay value.
        """
        # Collect the designation values.
        unique_designations = set(RecordModelUtil.get_value_list(
            RecordModelWrapperUtil.unwrap_list(aliquot_instructions),
            C_TestAliquotModel.C_DESIGNATION__FIELD_NAME.field_name))

        # Collect the experiment designations (exclude storage)
        unique_experiment_designations = unique_designations.copy()
        unique_experiment_designations.discard("Storage")

        # The collection of test aliquots can only have 1 Experiment Designation.
        if len(unique_experiment_designations) > 1:
            raise SapioUserErrorException("Please select test aliquots with a matching designation!")
        if len(unique_experiment_designations) == 0:
            raise SapioUserErrorException(
                "None of the selected test aliquots have a designation matching an experiment!")

        # Filter down to aliquots that will be launched into an experiment.
        experiment_aliquots: List[C_TestAliquotModel] = list()
        for aliquot in aliquot_instructions:
            if aliquot.get_C_Designation_field() != "Storage":
                experiment_aliquots.append(aliquot)

        # Ensure that at least some of the test aliquots are Ready.
        statuses = RecordModelUtil.get_value_list(
            RecordModelWrapperUtil.unwrap_list(experiment_aliquots),
            C_TestAliquotModel.C_STATUS__FIELD_NAME.field_name)
        if "Ready" not in statuses:
            raise SapioUserErrorException("None of the selected test aliquots designated for experiments are ready for processing!")

        # Filter the experiment aliquots down to aliquots which are ready.
        ready_aliquots: List[C_TestAliquotModel] = list()
        for aliquot in experiment_aliquots:
            if aliquot.get_C_Status_field() == "Ready":
                ready_aliquots.append(aliquot)

        # Ensure that every test aliquot has a unique source sample.
        unique_sample_ids: Set[str] = set()
        for aliquot in ready_aliquots:
            sample_id = aliquot.get_C_SampleId_field()
            if sample_id in unique_sample_ids:
                raise SapioUserErrorException("The test aliquots must all have unique source samples.")
            unique_sample_ids.add(sample_id)

        # Ensure that every test aliquot has the same Assay value.
        unique_assay_values: Set[str] = set()
        for aliquot in ready_aliquots:
            unique_assay_values.add(aliquot.get_C_Assay_field())
        if len(unique_assay_values) > 1:
            raise SapioUserErrorException("The test aliquots must all have the same assay.")

    def check_for_warnings(self, aliquot_instructions):
        """
        Warns in the following cases:
        - If some of the selected test aliquots are designated for storage.
        - If some of the selected test aliquots designated for an experiment are not ready.
        """
        # Compile the designations for the selected test aliquots.
        designations = RecordModelUtil.get_value_list(
            RecordModelWrapperUtil.unwrap_list(aliquot_instructions),
            C_TestAliquotModel.C_DESIGNATION__FIELD_NAME.field_name)

        # Warn the user if some of the aliquots are designated for storage and are to be excluded.
        if "Storage" in designations:
            # Count how many test aliquots are designated for storage.
            storage_count = len([designation for designation in designations if designation == "Storage"])
            okay: bool = self.callback.yes_no_dialog("Storage Test Aliquots Detected", str(storage_count)
                                                          + " of the selected test aliquots are "
                                                          + "designated for storage and will be excluded from"
                                                          + " the experiment. Would you like to continue?")
            if not okay:
                raise SapioUserCancelledException()

        # Filter the next check down to aliquots intended for the experiment.
        experiment_aliquots: List[C_TestAliquotModel] = list()
        for aliquot in aliquot_instructions:
            if aliquot.get_C_Designation_field() != "Storage":
                experiment_aliquots.append(aliquot)

        # Check to see if any of the chosen aliquots are ready.
        statuses = RecordModelUtil.get_value_list(
            RecordModelWrapperUtil.unwrap_list(experiment_aliquots),
            C_TestAliquotModel.C_STATUS__FIELD_NAME.field_name)
        # Check on non-ready statuses and prompt.
        unique_statuses = set(statuses)
        if len(unique_statuses) > 1:
            # Count how many statuses aren't ready.
            non_ready_statuses = len([status for status in statuses if status != "Ready"])
            okay: bool = self.callback.yes_no_dialog("Multiple statuses detected", str(non_ready_statuses)
                                                          + " of the test aliquots designated for an experiment are not"
                                                          + " ready for processing"" and will be excluded from the "
                                                          + "experiment. Would you like to continue?")
            if not okay:
                raise SapioUserCancelledException()

    def get_valid_aliquots(self, aliquot_instructions):
        """
        Filters the list of test aliquots to only include those that are valid for the experiment. The valid aliquots
        will:
        - Have a designation other than "Storage".
        - Have a status of "Ready".
        """
        valid_aliquots: List[C_TestAliquotModel] = list()
        for aliquot in aliquot_instructions:
            if aliquot.get_C_Status_field() == "Ready" and aliquot.get_C_Designation_field() != "Storage":
                valid_aliquots.append(aliquot)
        return valid_aliquots


class TestAliquotHandler:
    """
    This Handler stores the 4 functions that are used to launch the Test Aliquot designated experiments.

    Currently, includes HPLC and ELISA.

    """

    context: SapioWebhookContext
    experiment_handler: ExperimentHandler
    record_handler: RecordHandler

    def __init__(self, context: SapioWebhookContext, experiment: ElnExperiment | None = None):
        self.context = context
        self.record_handler = RecordHandler(context)
        if experiment is not None:
            self.experiment_handler = ExperimentHandler(context, experiment=experiment)

    def set_experiment(self, experiment: ElnExperiment):
        self.experiment_handler = ExperimentHandler(self.context, experiment=experiment)

    def convert_test_aliquots_to_samples(self, test_aliquots: List[C_TestAliquotModel]):
        """
        For each test aliquot, treat the test aliquot as an instruction for how to create a sample aliquot.
        The aliquot id will be generated based on the test aliquots sapmle id and aliquot number. The sample aliquot and
        the test aliquot record will both have a status of "In Process". The test aliquot will have a side link to the
        sample aliquot.

        :param test_aliquots: The list of test aliquots to create sample aliquots for.
        :returns: The list of sample aliquots that were created.
        """
        # Prepare the list of sample aliquots.
        sample_aliquots: List[SampleModel] = list()

        # Load relationships in bulk before iterating.
        rel_man = Manager.record_model_relationship_manager(self.context)
        rel_man.load_parents_of_type(test_aliquots, SampleModel)
        rel_man.load_forward_side_links(RecordModelWrapperUtil.unwrap_list(test_aliquots), C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name)
        for instruction in test_aliquots:
            # Create the aliquot sample, and link it to the test aliquot.
            source_sample: SampleModel = instruction.get_parent_of_type(SampleModel)
            if source_sample is None:
                raise SapioUserErrorException("The test aliquot for " + instruction.get_C_SampleId_field()
                                              + " with aliquot number " + str(instruction.get_C_AliquotNumber_field())
                                              + " does not have a parent sample.")
            new_aliquot: SampleModel = source_sample.add(Child.create(SampleModel))
            instruction.set_side_link(C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name, new_aliquot)

            # set the aliquot id on the new sample.
            new_aliquot.set_SampleId_field(instruction.get_C_TestAliquotSampleId_field())

            # Copy fields from source sample
            new_aliquot.set_IsControl_field(source_sample.get_IsControl_field())

            # Set other values.
            new_aliquot.set_OtherSampleId_field(instruction.get_C_OtherSampleId_field())
            new_aliquot.set_ExemplarSampleType_field(instruction.get_C_SampleType_field())
            new_aliquot.set_Volume_field(instruction.get_C_Volume_field())
            new_aliquot.set_VolumeUnits_field(instruction.get_C_VolumeUnits_field())
            new_aliquot.set_Concentration_field(instruction.get_C_EstimatedConcentration_field())
            new_aliquot.set_ConcentrationUnits_field(instruction.get_C_ConcentrationUnits_field())
            new_aliquot.set_ExemplarSampleStatus_field("In Process")

            # Update the status of the test aliquot.
            instruction.set_C_Status_field("In Process")

            # Add to our list.
            sample_aliquots.append(new_aliquot)

        return sample_aliquots

    def identify_samples(self, aliquot_instructions: List[C_TestAliquotModel]):
        """
        Identifies the Test Aliquots which are actually valid from the selection. Valid aliquots will have a status of
        "Ready", and a designation other than storage. If the selection contains aliquots that are not ready or are
        designated for storage, the user will be prompted to continue or cancel the operation. If the user decides to
        continue, then the invalid aliquots will be removed from the list of aliquots to process.

        :param aliquot_instructions: The list of test aliquots to check.
        :return: The list of valid test aliquots.
        """
        # Prepare the Validator.
        validator = TestAliquotValidator(self.context)
        # Run checks for hard errors.
        validator.check_for_hard_errors(aliquot_instructions)

        # Run checks for warnings.
        validator.check_for_warnings(aliquot_instructions)

        return validator.get_valid_aliquots(aliquot_instructions)

    def set_product(self, test_aliquots: List[C_TestAliquotModel], assay_details_model: ELNExperimentDetailModel | None = None):
        # Get the Studies for the selected aliquots.
        path_to_study = RelationshipPath().parent_type(SampleModel).ancestor_type(StudyModel)
        rel_man = Manager.record_model_relationship_manager(self.context)
        rel_man.load_path_of_type(test_aliquots, path_to_study)
        samples_to_studies: Dict[SampleModel, StudyModel] = self.record_handler.get_linear_path(test_aliquots,
                                                                                                path_to_study,
                                                                                                StudyModel)
        studies: Set[StudyModel] = set(samples_to_studies.values())
        studies.discard(None)

        # Comma delimit the unique "Product" values from the studies
        product_values = set()
        for study in studies:
            product_values.add(study.get_C_Product_field())
        product = ", ".join(product_values)
        self.__get_assay_details(assay_details_model).set_field_value("C_Product", product)

    def set_assay(self, source_aliquots: List[C_TestAliquotModel], assay_details_model: ELNExperimentDetailModel | None = None):
        assays = RecordModelUtil.get_value_list(self.record_handler.inst_man.unwrap_list(source_aliquots), C_TestAliquotModel.C_ASSAY__FIELD_NAME.field_name)
        assay_value = assays.pop()
        self.__get_assay_details(assay_details_model).set_field_value("C_Assay", assay_value)

    def set_assay_date(self, assay_details_model: ELNExperimentDetailModel | None = None):
        # Get the 'Assay Date' Value, which is Today's date.
        assay_date: int = TimeUtil.now_in_millis()
        self.__get_assay_details(assay_details_model).set_field_value("AssayDate", assay_date)

    def set_submitter(self, test_aliquots: List[C_TestAliquotModel], assay_details_model: ELNExperimentDetailModel | None = None):
        # Submitter is the user who created these test aliquots.
        created_by_values = set()
        for aliquot in test_aliquots:
            created_by_values.add(aliquot.get_CreatedBy_field())
        sorted_created_by_values = list(created_by_values)
        sorted_created_by_values.sort()
        submitter = ", ".join(sorted_created_by_values)
        self.__get_assay_details(assay_details_model).set_field_value("Submitter", submitter)

    def set_analyst(self, existing_details_model: ELNExperimentDetailModel | None = None):
        # Comma delimit the unique "Created By" values from the test aliquot records to get the "Analyst" value.
        self.__get_assay_details(existing_details_model).set_field_value("Analyst", self.context.user.username)


    def __get_assay_details(self, existing_detail: ELNExperimentDetailModel | None = None):
        """
        Returns the current detail. If none is passed in, it will retrieve the detail from the experiment.
        """
        if existing_detail:
            return existing_detail
        assay_step: ElnEntryStep = self.experiment_handler.get_step_by_option(ExperimentEntryTags.ASSAY_DETAILS)
        if assay_step is None:
            raise SapioUserErrorException("The experiment does not contain an assay details step. "
                                            + "Please contact a system administrator.")
        return self.experiment_handler.get_step_models(assay_step, ELNExperimentDetailModel).pop()

    def set_experiment_details(self, selected_aliquots: List[C_TestAliquotModel], assay_details_model: ELNExperimentDetailModel | None = None):
        """
        Update the step containing assay details within the experiment with the appropriate values. The step will be
        identified by the "ASSAY DETAILS" tag. The values are:
        - Products: The unique "Product" values from the studies of the selected aliquots.
        - Assay Date: Today's date.
        - Submitter: The current user.
        - Analyst: The unique "Created By" values from the test aliquot records.

        :param selected_aliquots: The list of test aliquots that were selected, used to populate the products and
            analyst fields.
        :return: nothing.
        """
        # Ensure we pass the same reference to avoid re-querying the same data.
        detail = self.__get_assay_details(assay_details_model)
        self.set_product(selected_aliquots, detail)
        self.set_assay_date(detail)
        self.set_submitter(selected_aliquots, detail)
        self.set_analyst(detail)
        self.set_assay(selected_aliquots, detail)

    def add_experiment_to_sample_studies(self, valid_aliquots: List[C_TestAliquotModel]):
        """
        Add the experiment to the studies of the selected aliquots.

        The experiment cannot be related to multiple studies, so it must be related to a NotebookDirectory which is a
        child of those studies instead. The directory will be named programmatically so that we can rely on the same
        directory being used for each permutation of studies.

        :param valid_aliquots: The list of test aliquots that were selected.
        :return: nothing.
        """
        # Get the Studies for the selected aliquots.
        path_to_study = RelationshipPath().parent_type(SampleModel).ancestor_type(StudyModel)
        samples_to_studies: Dict[SampleModel, StudyModel] = self.record_handler.get_linear_path(valid_aliquots, path_to_study, StudyModel)
        studies: Set[StudyModel] = set(samples_to_studies.values())
        studies.discard(None)

        # Get all the record IDS from the studies, and convert them into a sorted, distinct, list.
        # Then comma delimit them.
        record_ids = [study.record_id for study in studies]
        unique_ids = [str(x) for x in set(record_ids)]
        unique_ids.sort()
        study_ids = ", ".join(unique_ids)

        # Search for a NotebookDirectory with a DirectoryName equal to the joined study IDs.
        directories: List[NotebookDirectoryModel] = self.record_handler.query_models(
            NotebookDirectoryModel,
            NotebookDirectoryModel.DIRECTORYNAME__FIELD_NAME.field_name,
            [study_ids])

        # If there is an existing directory, use that. Otherwise, create a new directory.
        directory = None
        if len(directories) >= 1:
            directory = directories.pop()
        else:
            directory = self.record_handler.add_model(NotebookDirectoryModel)
            directory.set_DirectoryName_field(study_ids)
            # Relate to all studies.
            directory.add_parents(list(studies))

        # Move the experiment to the new directory.
        experiment_model: ELNExperimentModel = self.experiment_handler.get_experiment_model(ELNExperimentModel)
        self.record_handler.rel_man.load_parents_of_type([experiment_model], NotebookDirectoryModel)
        existing_parent = experiment_model.get_parent_of_type(NotebookDirectoryModel)
        if existing_parent is not None:
            existing_parent.remove_child(experiment_model)
        directory.add_child(experiment_model)

    def add_samples(self, sample_aliquots):
        """
        NOTE: This method invokes store and commit. All changes prior to this will be saved. This is to ensure that the
        samples exist before we add them in the ELN.
        """
        self.record_handler.rec_man.store_and_commit()
        samples_step: ElnEntryStep = self.experiment_handler.get_step("Samples")
        self.experiment_handler.add_step_records(samples_step, sample_aliquots)
        if samples_step.eln_entry.template_item_fulfilled_timestamp is None:
            self.experiment_handler.update_step(samples_step, template_item_fulfilled_timestamp=TimeUtil.now_in_millis())


class LaunchTestAliquots(CommonsWebhookHandler):
    """
    This webhook is intended to be invoked from the table toolbar context with a selection of test aliquots, to launch
    into the an experiment depending on the aliquots designation.

    Requirement Documentation:  https://onetakeda.atlassian.net/browse/ELNMSLAB-661
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
         # Prepare handlers.
        TimeUtil.set_default_timezone("EST")
        test_aliquot_handler = TestAliquotHandler(context)

        # Get the Test Aliquots.
        selected_aliquots: List[C_TestAliquotModel] = self.inst_man.add_existing_records_of_type(context.data_record_list, C_TestAliquotModel)
        valid_aliquots: List[C_TestAliquotModel] = test_aliquot_handler.identify_samples(selected_aliquots)

        # Create samples for those aliquots, and remove them from the queue here by updating status.
        sample_aliquots: List[SampleModel] = test_aliquot_handler.convert_test_aliquots_to_samples(valid_aliquots)

        # Determine which test has been assigned.
        designation = self.get_designation(valid_aliquots)

        # Grab the designated template, based on the designation.
        designation_manager = DesignationManager(context)
        designated_template: ElnTemplate | None = designation_manager.get_template(designation)
        if designated_template is None:
            raise SapioUserErrorException("No template found for the designation " + designation)

        # Create the new experiment.
        experiment_initialization_criteria = InitializeNotebookExperimentPojo(designated_template.display_name, designated_template.template_id)
        new_experiment = context.eln_manager.create_notebook_experiment(experiment_initialization_criteria)
        test_aliquot_handler.set_experiment(new_experiment)

        # Set the experiment details on the new experiment.
        test_aliquot_handler.set_experiment_details(selected_aliquots)

        # Add Experiment to sample studies
        test_aliquot_handler.add_experiment_to_sample_studies(valid_aliquots)

        # Add samples to the experiment (creating the records before we can actually add them)
        test_aliquot_handler.add_samples(sample_aliquots)

        # Send the user to the new experiment.
        return SapioWebhookResult(True, directive=ElnExperimentDirective(new_experiment.notebook_experiment_id))

    def get_designation(self, valid_aliquots):
        return set(RecordModelUtil.get_value_list(RecordModelWrapperUtil.unwrap_list(valid_aliquots),
                                                  C_TestAliquotModel.C_DESIGNATION__FIELD_NAME.field_name)).pop()


