from typing import List, Dict, Set

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.general.exceptions import SapioUserErrorException
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.DataMgmtService import DataMgmtServer
from sapiopylib.rest.pojo.DataRecord import DataRecord
from sapiopylib.rest.pojo.datatype.DataType import DataTypeHierarchy
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookEnums import SearchType
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.recordmodel.RecordModelUtil import RecordModelUtil
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import RecordModelWrapperUtil

from sapio.enum.pick_list import ReviewStatuses
from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import SampleModel, ELNExperimentModel, StudyModel
from sapio.model.eln_classes import ELNExperiment

CREATE_NEW = "Create New"
ADD_EXISTING = "Add Existing"


def parse_mapping_option(new_field_value_mapping: str) -> Dict[str, str]:

    # Handle when the tag hasn't been set properly.
    if not new_field_value_mapping:
        return dict()

    # Parse out the individual assignments, which are delimited by ';'
    mapping_instructions: List[str] = new_field_value_mapping.split(";")
    final_mappings = dict()
    for instruction_text_value in mapping_instructions:
        # Parse out the name and value, which are separated by '='
        instruction_parameters = instruction_text_value.split("=")
        # Skip invalid instructions.
        if len(instruction_parameters) < 2:
            continue
        field_name = instruction_parameters[0].strip()
        field_value = instruction_parameters[1].strip()
        final_mappings[field_name] = field_value
    return final_mappings


class CustomAddSamplesButton(CommonsWebhookHandler):
    """
    This button is a custom button for adding sample records to sample entries. There are two options
    - Add existing: This will show an input selection dialog to bring in samples existing in the system.
    - Create new: This will prompt you for how many samples to create, and then create new samples and add them to the
        entry
    """
    experiment_handler: ExperimentHandler
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Cache the experiment handler for consistency
        self.experiment_handler = ExperimentHandler(context)

        experiment_model: ELNExperimentModel = self.experiment_handler.get_experiment_model(ELNExperimentModel)
        status: str = experiment_model.get_field_value(ELNExperiment.REVIEW_STATUS)

        if status and status != ReviewStatuses.OPEN:
            return SapioWebhookResult(False, "Samples cannot be added to an experiment that is not in an Open status!")

        # Option dialog.
        choice: str = CallbackUtil(context).option_dialog("Add Samples to Experiment", "How do you want to add these samples?", [
            ADD_EXISTING, CREATE_NEW], user_can_cancel=True)

        samples_to_add = None
        # Add existing
        if choice == ADD_EXISTING:
            samples_to_add = self.prompt_for_existing_samples()

        # create new
        if choice == CREATE_NEW:
            samples_to_add: List[SampleModel] = self.prompt_for_create_new()
            self.rec_man.store_and_commit()

        # Handle options that don't exist.
        if samples_to_add is None:
            return SapioWebhookResult(False, "Invalid selection made.")

        # Add those samples to the entry.
        sample_records: List[DataRecord] = RecordModelUtil.get_data_record_list(RecordModelWrapperUtil.unwrap_list(samples_to_add))
        self.experiment_handler.add_step_records(context.experiment_entry.entry_name, sample_records)

        # all done
        return SapioWebhookResult(True, "Success!")

    def prompt_for_existing_samples(self):
        samples_to_add: List[SampleModel] = CallbackUtil(self.context).input_selection_dialog(SampleModel, "Choose existing samples to bring in.",
                                                          search_types=[SearchType.QUICK_SEARCH, SearchType.ADVANCED_SEARCH, SearchType.BROWSE_TREE])

        return samples_to_add

    def prompt_for_create_new(self):
        num_to_create: int = CallbackUtil(self.context).integer_input_dialog("Create Samples", "How many samples should be created?", "Number to Create", default_value=1, min_value=1)

        # Use the "NEW SAMPLE FIELD VALUES" value to determine what values to set on the samples.
        options = self.experiment_handler.get_step_options(self.context.experiment_entry.entry_name)
        fields_to_set: Dict[str, str] = dict()
        if options:
            new_field_value_mapping = options.get(ExperimentEntryTags.NEW_SAMPLE_FIELD_VALUES)
            fields_to_set = parse_mapping_option(new_field_value_mapping)

        # If the sample type isn't specified in the tag, attempt to populate it with the other samples sample types.
        if SampleModel.EXEMPLARSAMPLETYPE__FIELD_NAME.field_name not in fields_to_set:
            samples: List[SampleModel] = self.experiment_handler.get_step_models(self.context.experiment_entry.entry_name, SampleModel)
            sample_types: List[str] = RecordModelUtil.get_value_list(RecordModelWrapperUtil.unwrap_list(samples), SampleModel.EXEMPLARSAMPLETYPE__FIELD_NAME.field_name)
            sample_types: Set[str] = set(sample_types)
            if len(sample_types) == 1:
                fields_to_set[SampleModel.EXEMPLARSAMPLETYPE__FIELD_NAME.field_name] = sample_types.pop()

        # add them!
        samples: List[SampleModel] = self.inst_man.add_new_records_of_type(num_to_create, SampleModel)
        for sample in samples:
            for field_name, field_value in fields_to_set.items():
                sample.set_field_value(field_name, field_value)

        # Find the experiments parent study, and add the samples to it.
        experiment_model = self.experiment_handler.get_experiment_model(ELNExperimentModel)
        self.rel_man.load_parents_of_type([experiment_model], StudyModel)
        study = experiment_model.get_parent_of_type(StudyModel)
        if study is not None:
            study.add_children(samples)

        return samples
