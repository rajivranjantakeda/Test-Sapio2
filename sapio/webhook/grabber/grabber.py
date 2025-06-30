import re
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.general.exceptions import SapioUserCancelledException, SapioUserErrorException
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.datatype.FieldDefinition import VeloxStringFieldDefinition, AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.eln.ExperimentEntry import ExperimentEntry
from sapiopylib.rest.pojo.eln.SapioELNEnums import ExperimentEntryStatus, TemplateAccessLevel
from sapiopylib.rest.pojo.eln.eln_headings import ElnExperimentTabAddCriteria, ElnExperimentTab
from sapiopylib.rest.pojo.eln.protocol_template import ProtocolTemplateQuery, ProtocolTemplateInfo
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookDirective import ExperimentEntryDirective
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep, ElnExperimentProtocol, ProtocolStepType
from sapiopylib.rest.utils.recordmodel.PyRecordModel import PyRecordModel
from sapiopylib.rest.utils.recordmodel.properties import Child
from sapiopylib.rest.PicklistService import PicklistManager
from sapiopylib.rest.pojo.eln.ElnEntryPosition import ElnEntryPosition

from sapio.enum.tags import ExperimentEntryTags, ProtocolTemplateTags
from sapio.model.data_type_models import SampleModel, ELNSampleDetailModel, ELNExperimentDetailModel, C_ProcessStepModel, ELNExperimentModel
from sapio.model.eln_classes import ELNSampleDetail
from sapio.webhook.grabber.grabber_context import CustomGrabberContext, CustomGrabberContextBuilder
from sapio.webhook.util.takeda_utils import ElnPositionUtil

# Constants
NUMBER_OF_REPLICATES = "NumberOfReplicates"

SAMPLE_DETAIL_FIELD_MAPPINGS = {
    SampleModel.ISCONTROL__FIELD_NAME.field_name: "IsControl",
    SampleModel.SAMPLEID__FIELD_NAME.field_name: "SampleId",
    SampleModel.OTHERSAMPLEID__FIELD_NAME.field_name: "OtherSampleId"
}

# Possible fields that need to have the phase/step value set
PHASE_STEP_FIELDS = ["PhaseStep", "PassagingToStep"]


# Utility functions
def get_tagged_protocols_by_display_name(protocols: List[ProtocolTemplateInfo], tag_key: str) -> Dict[str, ProtocolTemplateInfo]:
    """Fetch protocols tagged with a specific key or with the static value 'Universal'."""
    return {
        protocol.display_name: protocol
        for protocol in protocols
        if f"{ProtocolTemplateTags.BUILDING_BLOCK}{tag_key}".lower() in protocol.description.lower()
        or f"{ProtocolTemplateTags.BUILDING_BLOCK}Universal".lower() in protocol.description.lower()
    }


def sort_protocol_by_ending_number(protocol: ProtocolTemplateInfo) -> int:
    """Sort protocols by the ending number in their template name."""
    match = re.search(r'\d+$', protocol.template_name)
    return int(match.group()) if match else 0


def title_input_prompt(protocol: ProtocolTemplateInfo, context: SapioWebhookContext) -> str:
    """
    Displays an input dialog with a text field for entering a title.

    Args:
        protocol (ProtocolTemplateInfo): The selected protocol information.
        context (SapioWebhookContext): The current webhook context.

    Returns:
        str: The title entered by the user.

    Raises:
        SapioUserCancelledException: If the user cancels the input dialog.
    """
    compiled_regex = re.compile(ProtocolTemplateTags.TITLE_PROMPT_TAG_REGEX)
    matches = compiled_regex.findall(protocol.description)

    if not matches:
        return ""  # Return empty string if no title prompt tag exists

    # Extract display and message content
    match: tuple[str, str] = matches.pop()
    title_display, message_display = match

    # Create the title input field
    title_field = VeloxStringFieldDefinition("Title", "Title", "Title")
    title_field.editable = True

    # Prompt user input
    title: Optional[str] = CallbackUtil(context).input_dialog(title_display, message_display, title_field)

    if not title:
        raise SapioUserCancelledException("Title input was canceled by the user.")

    return title


def get_hardcoded_title(chosen_protocol: ProtocolTemplateInfo) -> str:
    """
    Handles a specific title tag in the protocol description.

    Args:
        chosen_protocol (ProtocolTemplateInfo): The selected protocol.

    Returns:
        str: The hardcoded title extracted from the protocol.

    Raises:
        SapioUserCancelledException: If no title is found or the title is invalid.
    """
    compiled_regex = re.compile(ProtocolTemplateTags.TITLE_SPECIFIC_TAG_REGEX)
    matches = compiled_regex.findall(chosen_protocol.description)

    if not matches:
        return ""  # Return empty if no specific title tag exists

    title = matches.pop()

    if not title:
        raise SapioUserCancelledException("Hardcoded title is missing or invalid.")

    return title

def picklist_title_prompt(chosen_protocol: ProtocolTemplateInfo, context: SapioWebhookContext) -> str:
    """
    Displays an input dialog with a list of selectable titles from a picklist.

    Args:
        chosen_protocol (ProtocolTemplateInfo): The selected protocol.
        context (SapioWebhookContext): The current webhook context.

    Returns:
        str: The selected title from the picklist.

    Raises:
        SapioUserCancelledException: If the user cancels the dialog or no valid selection is made.
    """
    compiled_regex = re.compile(ProtocolTemplateTags.TITLE_PICKLIST_PROMPT_TAG_REGEX)
    matches = compiled_regex.findall(chosen_protocol.description)

    if not matches:
        return ""  # Return empty if no picklist tag exists

    picklist_name, title_display = matches.pop()

    picklist_manager = PicklistManager(context.user)
    picklist_options = picklist_manager.get_picklist(picklist_name=picklist_name).entry_list

    if not picklist_options:
        raise SapioUserErrorException("Picklist options are missing or empty.")

    selected_title = CallbackUtil(context).list_dialog(title_display, picklist_options, multi_select=False)

    if not selected_title:
        raise SapioUserCancelledException("Picklist selection was canceled by the user.")

    return selected_title[0]


class ProtocolGrabber(CommonsWebhookHandler, ABC):
    """
    A base class for protocol grabbers. webhooks extending this base class are intended to be Grabber webhooks.
    This class will find the protocols with a certain tag value in the protocol description, prompt the user for a
    particular protocol and title (optionally) and create the entries. It will also relate any new sample detail entries
    to the most recent samples entry, and create sample details for those samples.

    This Grabber webhook supports being invoked either by an eln grabber invocation, or by an ELN main toolbar button.
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Build the context that will be needed for any custom grabber to use.
        context_builder = CustomGrabberContextBuilder()

        # Pass the experiment handler into our custom context.
        context_builder.experiment_handler(self.exp_handler)

        # Prompt the user for the protocol to use.
        protocols: List[ProtocolTemplateInfo] = context.eln_manager.get_protocol_template_info_list(ProtocolTemplateQuery(whitelist_access_levels=[TemplateAccessLevel.PUBLIC]))
        tagged_protocols = get_tagged_protocols_by_display_name(protocols, self.get_tag_regex())
        chosen_protocol = self.prompt_for_protocol(tagged_protocols)
        context_builder.protocol(chosen_protocol)

        # Get the title for the protocol.
        title = self.get_title(chosen_protocol)
        context_builder.title(title)

        # Get the tabs, and the current steps.
        ordered_tabs: list[ElnExperimentTab] = self.context.eln_manager.get_tabs_for_experiment(self.context.eln_experiment.notebook_experiment_id)
        ordered_tabs.sort(key=lambda tab: tab.tab_order)
        existing_steps: List[ElnEntryStep] = self.context.active_protocol.get_sorted_step_list()

        # Find the most recent samples entry.
        current_position = self.get_current_position(existing_steps)
        sample_entry = self.get_most_recent_samples_table(ordered_tabs, existing_steps, current_position)
        context_builder.sample_step(sample_entry)

        # Retrieve the samples from the sample step.
        samples: List[SampleModel] | None = self.get_samples(sample_entry)
        context_builder.source_samples(samples)

        # Handle sample count enforcement.
        if not self.enforce_sample_count_limit(chosen_protocol, samples, sample_entry):
            return SapioWebhookResult(False)

        # Create the entries using that protocol.
        protocol_destination = self.calculate_protocol_destination(chosen_protocol, context, existing_steps, ordered_tabs, title)
        created_entries: List[ExperimentEntry] = context.eln_manager.add_protocol_template(context.eln_experiment.notebook_experiment_id, chosen_protocol.template_id, protocol_destination)
        context_builder.created_entries(created_entries)

        # Update the sample detail entries to be dependent on the sample table.
        self.update_created_entries(chosen_protocol, created_entries, sample_entry, title)

        # Gather the sample detail tables that need to be populated
        sample_detail_entries: List[ExperimentEntry] = self.get_sample_detail_entries(sample_entry, created_entries)

        # Always retrieve the field definitions for the experiment entries.
        fields_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]] = self.get_entry_field_definitions()
        context_builder.field_definitions(fields_by_entry_id)

        # Create the sample details.
        sample_details: Dict[int, List[PyRecordModel]] = self.populate_sample_detail_tables(sample_detail_entries, samples, fields_by_entry_id)
        context_builder.sample_details(sample_details)

        built_context: CustomGrabberContext = context_builder.build()
        self.update_entry_records(built_context, fields_by_entry_id)

        # Run any custom logic.
        self.execute_custom_logic(built_context)

        # Create a process record for each building block
        self.create_process_step_record(built_context)

        # Set initial sample values in the first entry of the block
        self.set_initial_load_values(built_context, fields_by_entry_id, sample_details)

        # All done.
        self.rec_man.store_and_commit()
        directive_to_first_entry = ExperimentEntryDirective(context.eln_experiment.notebook_experiment_id, created_entries[0].entry_id)

        return SapioWebhookResult(True, "Success!", directive=directive_to_first_entry)

    def calculate_protocol_destination(self, chosen_protocol, context, existing_steps, ordered_tabs, title):
        protocol_destination = None
        if self.is_eln_main_toolbar():
            existing_entries_ids = [step.eln_entry.entry_id for step in existing_steps]

            # Determine the tab name based on the prefix count
            tab_name = self.get_tab_name(chosen_protocol, title, ordered_tabs)

            # Add the tab to the experiment
            tab_criteria = ElnExperimentTabAddCriteria(tab_name, existing_entries_ids)
            new_tab: ElnExperimentTab = self.context.eln_manager.add_tab_for_experiment(context.eln_experiment.notebook_experiment_id, tab_criteria)

            # Use new tab position.
            protocol_destination = ElnEntryPosition(new_tab.tab_id, 0)
        elif self.is_eln_menu_grabber():
            protocol_destination = self.context.entry_position
        else:
            raise SapioUserErrorException("This webhook has been configured incorrectly. "
                                          + "Please contact a system administrator.")
        return protocol_destination

    def create_process_step_record(self, context: CustomGrabberContext):
        # Create a new Process Step data record.
        process_step: C_ProcessStepModel = self.inst_man.add_new_record_of_type(C_ProcessStepModel)

        # Make the new process step a child of the experiment.
        experiment_model: ELNExperimentModel = context.experiment_handler.get_experiment_model(ELNExperimentModel)
        experiment_model.add_child(process_step)

        # Set the Process Step value.
        process_step.set_C_ProcessStep_field(context.title)

    def get_current_position(self, current_steps: List[ElnEntryStep]) -> ElnEntryPosition:
        """
        Get the position which should be used as the current position. When invoked from the main toolbar, this will
        return the position of the very last step. When invoked from a grabber, this will return the position of the
        grabber.

        :param current_steps: The current steps in the experiment, in sorted order.
        :returns: The position to use as the current position.
        """
        if self.is_eln_main_toolbar():
            last_step = current_steps[-1]
            return ElnPositionUtil.to_position(last_step)
        elif self.is_eln_menu_grabber():
            # If using a grabber, iterate over the steps and grab the last entry before this position.
            return self.context.entry_position
        else:
            raise SapioUserErrorException("This webhook has been configured incorrectly. Please contact a system administrator.")

    @abstractmethod
    def get_tag_regex(self):
        pass

    @abstractmethod
    def execute_custom_logic(self, context: CustomGrabberContext):
        pass

    def prompt_for_protocol(self, cell_culture_protocols):
        """
        Displays a list dialog to select a relevant protocol.
        """
        # Get the display values sorted by the hidden template name.
        protocols: List[ProtocolTemplateInfo] = list(cell_culture_protocols.values())
        protocols.sort(key=sort_protocol_by_ending_number)
        protocol_display_values = [protocol.display_name for protocol in protocols]

        # Run the prompt.
        choices: List[str] = CallbackUtil(self.context).list_dialog("Which protocol would you like to try?", protocol_display_values, False)

        # Process the choice, and return the chosen protocol.
        if len(choices) < 1:
            raise SapioUserCancelledException()
        choice = choices.pop()
        chosen_protocol: ProtocolTemplateInfo = cell_culture_protocols.get(choice)
        return chosen_protocol

    def get_tab_name(self, chosen_protocol: ProtocolTemplateInfo, title: str, tabs: List[ElnExperimentTab]) -> str:
        """
        Determine the tab name based on the prefix count.
        """
        if title:
            # get the tabs names that are already in the experiment
            new_tab_name = title
            if len(tabs) > 0:
                tab_names: list[str] = []
                for tab in tabs:
                    tab_names.append(tab.tab_name)
                tab_names.reverse()  # Reversed to get the most recent entries first that will have a higher number in brackets.
                for tab_name in tab_names:
                    if new_tab_name in tab_name:
                        pattern = re.compile(rf'^{re.escape(title)}(?: \((\d+)\))?$')
                        match = pattern.match(tab_name)
                        if match:
                            if match.group(1):
                                new_tab_name = new_tab_name + f" ({str(int(match.group(1)) + 1)})"
                            else:
                                new_tab_name = f"{new_tab_name} (2)"
                            break
            return new_tab_name
        return chosen_protocol.display_name

    def update_created_entries(self, protocol_template: ProtocolTemplateInfo, new_entries: List[ExperimentEntry], sample_entry: ProtocolStepType, title: str):
        """
        Executes O(n) webservice calls to update entries where 'n' is the number of new entries. If there is a title,
        then all entries need to be updated. Otherwise, only sample detail entries will be updated.
        """
        eln_protocol = ElnExperimentProtocol(self.context.eln_experiment, self.context.user)

        # Get the current entries for the experiment.
        current_entries: List[ElnEntryStep] = self.exp_handler.get_all_steps()
        created_entry_ids: list[int] = [entry.entry_id for entry in new_entries]
        current_entry_names: list[str] = [entry.get_name() for entry in current_entries if entry.get_id() not in created_entry_ids]
        current_entry_names.reverse() # Reversed to get the most recent entries first that will have a higher number in brackets.

        # Iterate over all of the created entries.
        for new_entry in new_entries:
            new_entry_name = new_entry.entry_name  # Default to the original entry name
            for name in current_entry_names:
                if title:
                    new_entry_name = "".join(("(" + title + ") - ", new_entry.entry_name))
                # Use a regular expression to match the entire entry name, including the optional prefix and suffix
                pattern = re.compile(rf'^{re.escape(new_entry_name)}(?: \((\d+)\))?$')
                match = pattern.match(name)
                if match:
                    suffix = match.group(1)
                    if suffix:
                        new_entry_name = new_entry_name + f" ({str(int(suffix) + 1)})"
                        break
                    else:
                        new_entry_name = new_entry_name + " (2)"
                        break

            # Update each entry.
            new_entry_protocol = ElnEntryStep(eln_protocol, new_entry)
            if new_entries[0].entry_id == new_entry.entry_id:
                # Update the first entry with a tag indicating that it is the first entry for a given building block.
                self.update_entry(new_entry_protocol, sample_entry, new_entry_name, title, protocol_template.display_name)
            else:
                self.update_entry(new_entry_protocol, sample_entry, new_entry_name, title)

    def update_entry(self, new_entry_protocol: ElnEntryStep, sample_entry: ElnEntryStep, updated_entry_name: str, title: str, protocol_template: str | None = None):
        """
        Sometimes executes a webservice call to update the entry. Sample Detail entries are always updated. Other
        entries are only updated if their name needs to be updated.
        """
        entry_options = new_entry_protocol.get_options()

        # Set the phase/step on the entry option for later reference
        entry_options.update({ExperimentEntryTags.PHASE_STEP: title})
        if protocol_template:
            entry_options.update({ExperimentEntryTags.SOURCE_BUILDING_BLOCK: protocol_template})

        if ExperimentEntryTags.TEST_ALIQUOTS in entry_options:
            entry_options.update({ExperimentEntryTags.TEST_ALIQUOTS: title})

        # This entry creates sample aliquots, which should get a sample type set to the selected phase/step
        if ExperimentEntryTags.CREATE_SAMPLE_ALIQUOT_ENTRY in entry_options:
            self.add_output_sample_type(entry_options, title)

        if "ELNSampleDetail" in new_entry_protocol.eln_entry.data_type_name and sample_entry is not None:
            # Update Dependencies if the sample detail does not have a dependency already
            updated_dependency_set = None
            updated_related_entry_set = None
            if new_entry_protocol.eln_entry.dependency_set is None or not new_entry_protocol.eln_entry.dependency_set:
                updated_dependency_set = [sample_entry.eln_entry.entry_id]
                updated_related_entry_set = [sample_entry.eln_entry.entry_id]

            # Set as disabled
            updated_status: ExperimentEntryStatus = ExperimentEntryStatus.Disabled

            # Use eln manager to update, but update the steps in ExperimentHandler if the name has been changed.
            self.exp_handler.update_step(new_entry_protocol, entry_name=updated_entry_name,
                                         dependency_set=updated_dependency_set,
                                         related_entry_set=updated_related_entry_set,
                                         entry_status=updated_status,
                                         entry_options_map=entry_options)
        else:
            # Don't update normal entries when there's nothing to update.
            self.exp_handler.update_step(new_entry_protocol, entry_name=updated_entry_name, entry_options_map=entry_options)

    def get_most_recent_samples_table(self,
                                      tabs: List[ElnExperimentTab],
                                      existing_steps: List[ElnEntryStep],
                                      max_position: ElnEntryPosition):
        """
        Retrieves the most recent sample table on this tab, inclusive of the max_position parameter.

        :param tabs: The list of tabs currently in the experiment.
        :param existing_steps: The list of existing steps in the experiment.
        :param max_position: The position to stop looking for the sample table.
        :returns: The last sample entry before the parameter entry, across tabs.
        """
        sample_entry:  ProtocolStepType | None = None
        for potential_sample_step in existing_steps:
            # Once we've exceeded the max position, we can stop looking.
            potential_position = ElnPositionUtil.to_position(potential_sample_step)
            if ElnPositionUtil.is_after(tabs, potential_position, max_position):
                break
            if SampleModel.DATA_TYPE_NAME in potential_sample_step.get_data_type_names():
                sample_entry = potential_sample_step
        return sample_entry

    def populate_sample_detail_tables(self, sample_detail_entries: List[ExperimentEntry], samples: List[SampleModel] | None, field_defs_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]]) -> Dict[int, List[PyRecordModel]]:
        """
        Populates all the sample detail tables in the list of created entry. Each sample detail entry will have 1
        sample detail per sample.

        :param sample_detail_entries: All the sample detail entries to populate with sample details.
        :param samples: The samples from the sample entry to create sample details for.
        :returns: A dictionary where the key is the entry id of the sample detail entry, and the value is a list of
            that entries sample detail records.
        """
        # if there are no samples, then no sample details will be made. return empty result.
        if samples is None or len(samples) < 1:
            return dict()

        # Populate the sample details, and copy applicable sample detail fields.
        # Return the created details, mapped by entry id.
        detail_map: Dict[int, List[PyRecordModel]] = dict()
        for entry in sample_detail_entries:

            # Compile the viable sample detail field names on this sample detail entry
            sample_detail_fields: List[AbstractVeloxFieldDefinition] = field_defs_by_entry_id.get(entry.entry_id)
            field_names: List[str] = list()
            for sample_detail_field in sample_detail_fields:
                field_names.append(sample_detail_field.data_field_name)

            for sample in samples:
                detail = sample.add(Child.create_by_name(entry.data_type_name))
                # Copy the sample value for each mapping to the sample detail field.
                for sample_field, sample_detail_field in SAMPLE_DETAIL_FIELD_MAPPINGS.items():
                    value = sample.get_field_value(sample_field)
                    if sample_detail_field in field_names:
                        detail.set_field_value(sample_detail_field, value)
                # Default number of replicates to 1.
                if NUMBER_OF_REPLICATES in field_names:
                    detail.set_field_value(NUMBER_OF_REPLICATES, 1)

                # Append to map.
                detail_map.setdefault(entry.entry_id, []).append(detail)

        return detail_map

    def get_samples(self, sample_entry: ElnEntryStep) -> List[SampleModel] | None:
        """
        Retrieve the samples from the samples step.

        :param sample_entry: The ElnEntryStep for the sample entry to retrieve samples from.
        :returns: a list of SampleModels for the sample entry, or None if the sample entry is None.
        """
        if sample_entry is None:
            return None
        return self.exp_handler.get_step_models(sample_entry, SampleModel)

    def get_sample_detail_entries(self, sample_entry: ProtocolStepType, entries: List[ExperimentEntry]):
        """
        For the given sample entry and a list of entries, return the list of sample detail entries which are dependent
        on this sample entry.
        """
        sample_detail_entries = list()
        for created_entry in entries:
            if "ELNSampleDetail" in created_entry.data_type_name:
                for dependency_id in created_entry.dependency_set:
                    if dependency_id == sample_entry.get_id():
                        sample_detail_entries.append(created_entry)
        return sample_detail_entries
        pass

    def get_entry_field_definitions(self) -> Dict[int, List[AbstractVeloxFieldDefinition]]:
        # Compile the entries with field definitions.
        field_defs_by_id: Dict[int, List[AbstractVeloxFieldDefinition]] = dict()
        entries_with_field_defs = self.context.eln_manager.get_experiment_entry_list(self.context.eln_experiment.notebook_experiment_id, True)
        # TODO: Perhaps there will be a better bulk invocation to get field definitions. This will only return field definitions for
        #  ELN types at the moment.
        for entry in entries_with_field_defs:
            if hasattr(entry, "field_definition_list"):
                field_defs_by_id[entry.entry_id] = entry.field_definition_list
            else:
                field_defs_by_id[entry.entry_id] = list()
        return field_defs_by_id

    def get_title(self, chosen_protocol: ProtocolTemplateInfo) -> str:
        """
        There are currently 3 supported tags for titling methods. The three supported methods are:
            1. A free text prompt.
            2. A picklist prompt.
            3. A hardcoded title.
        The tags are checked in this order, and the first matched tag is returned.
        """

        # Check against text prompt tag.
        title = title_input_prompt(chosen_protocol, self.context)
        if title:
            return title

        # Check against picklist prompt tag.
        title = picklist_title_prompt(chosen_protocol, self.context)
        if title:
            return title

        # Check against hardcoded title tag.
        title = get_hardcoded_title(chosen_protocol)

        # Title is required. If we do not have a title at this point, the building block has been misconfigured.
        if not title:
            raise SapioUserErrorException("This building block is misconfigured, and is missing a title. "
                                          + "Please contact a system administrator.")

        return title

    def add_output_sample_type(self, entry_options, title):
        """
        Add an output sample type to an entry matching the user selected phase/step (title).
        :param entry_options:
        :param title:
        :return:
        """

        # If the output sample type is already set, then do not overwrite it
        if ExperimentEntryTags.OUTPUT_SAMPLE_TYPE_FOR_ALIQUOT in entry_options:
            return

        entry_options.update({ExperimentEntryTags.OUTPUT_SAMPLE_TYPE_FOR_ALIQUOT: title})

    def set_fields_for_records(self, entry: ExperimentEntry, entry_protocol: ElnEntryStep, field_names: List[str], entry_field_defs: List[AbstractVeloxFieldDefinition], title: str,  records: List[PyRecordModel] = None):
        """
        Sets specified fields to the given title for all records in the provided entry if the fields exist.

        :param entry_field_defs: Field definitions for the updated experiemnt entry
        :param entry: The experiment entry whose records need updating.
        :param entry_protocol: The protocol step associated with the entry.
        :param field_names: A list of field names to update.
        :param title: The title to set for the specified fields.
        :param records: Optional list of records to update directly.
        """
        if not records:
            if entry.data_type_name.lower().startswith(ELNSampleDetailModel.DATA_TYPE_NAME.lower()):
                records = self.exp_handler.get_step_models(entry_protocol, ELNSampleDetailModel)
            elif entry.data_type_name.lower().startswith(ELNExperimentDetailModel.DATA_TYPE_NAME.lower()):
                records = self.exp_handler.get_step_models(entry_protocol, ELNExperimentDetailModel)
            else:
                return

        # Get field definitions for the current entry to check field availability
        available_field_names = {field_def.data_field_name for field_def in entry_field_defs}

        for record in records:
            for field_name in field_names:
                if field_name in available_field_names:
                    record.set_field_value(field_name, title)

    def set_sample_type_on_entry_records(self, context: CustomGrabberContext, new_entry_protocol, options, entry_field_defs: List[AbstractVeloxFieldDefinition], records: List[PyRecordModel] = None):
        """
        Sets the SAMPLE_TYPE_2 field on ELNSampleDetail records for the given entry protocol.

        :param entry_field_defs: Field definitions for the updated experiment entry
        :param new_entry_protocol: The protocol step associated with the entry.
        :param options: The options dictionary containing entry-specific configurations.
        :param records: Optional list of records to update directly.
        """

        # Get the option value for setting the sample type.
        option_value = options.get(ExperimentEntryTags.SET_SAMPLE_TYPE_ON_SAMPLE_DETAIL)

        if not records:
            records = self.exp_handler.get_step_models(new_entry_protocol, ELNSampleDetailModel)

        if not records:
            return

        # Get field definitions for the current entry to ensure SAMPLE_TYPE_2 exists.
        field_names = {field_def.data_field_name for field_def in entry_field_defs}

        if ELNSampleDetail.SAMPLE_TYPE_2 not in field_names:
            return

        # Determine how to set SAMPLE_TYPE_2 based on the option value.
        if option_value == "USE PREVIOUS":
            # Retrieve the most recent sample types if needed.
            most_recent_sample_types = self.get_most_recent_sample_types(context)

            for record in records:
                sample_id = record.get_field_value(ELNSampleDetail.SAMPLE_ID)
                sample_type = most_recent_sample_types.get(sample_id)

                if sample_type:
                    record.set_field_value(ELNSampleDetail.SAMPLE_TYPE_2, sample_type)
                else:
                    # Fallback to the sample record type if no recent type is found.
                    source_sample = next(
                        (s for s in context.source_samples if s.get_SampleId_field() == sample_id),
                        None
                    )
                    if source_sample:
                        record.set_field_value(ELNSampleDetail.SAMPLE_TYPE_2, source_sample.get_ExemplarSampleType_field())
        else:
            # Use the option value directly as the sample type.
            for record in records:
                record.set_field_value(ELNSampleDetail.SAMPLE_TYPE_2, option_value)

    def get_most_recent_sample_types(self, context: CustomGrabberContext) -> Dict[str, str]:
        """
        Collects the most recent sample types mapped by sample ID, based on the most recent sample table or sample detail table.

        Args:
            context (CustomGrabberContext): The grabber context containing experiment details.

        Returns:
            Dict[str, str]: A dictionary mapping sample IDs to their sample types.
        """
        # Retrieve all experiment steps in reverse order for analysis
        all_steps = context.experiment_handler.get_all_steps()
        created_ids = {entry.entry_id for entry in context.created_entries}
        all_steps.reverse()

        # Iterate over steps to find the most recent sample table or detail table
        for step in all_steps:
            # Skip steps that are already known
            if step.get_id() in created_ids:
                continue

            # Check for sample tables and retrieve source samples if available
            if step.eln_entry.data_type_name == SampleModel.DATA_TYPE_NAME:
                if context.source_samples:
                    return {
                        sample.get_SampleId_field(): sample.get_ExemplarSampleType_field()
                        for sample in context.source_samples
                    }

            # Check for sample detail tables and process their records
            if ELNSampleDetailModel.DATA_TYPE_NAME in step.eln_entry.data_type_name:
                sample_details = context.experiment_handler.get_step_models(step.eln_entry.entry_name, ELNSampleDetailModel)

                # Verify if SAMPLE_TYPE_2 field exists in the field definitions
                field_definitions = context.field_definitions.get(step.get_id(), [])
                field_names = {field_def.data_field_name for field_def in field_definitions}

                if ELNSampleDetail.SAMPLE_TYPE_2 in field_names:
                    return {
                        sample_detail.get_SampleId_field(): sample_detail.get_field_value(ELNSampleDetail.SAMPLE_TYPE_2)
                        for sample_detail in sample_details
                    }

        # Return an empty dictionary if no relevant sample types are found
        return {}

    def set_custom_field_on_entry_records(self, new_entry_protocol, options, records: List[PyRecordModel] = None):
        """
        Sets custom fields on ELNSampleDetailModel or ELNExperimentDetailModel records based on options.

        :param new_entry_protocol: The protocol step associated with the entry.
        :param options: The options dictionary containing entry-specific configurations.
        :param records: Optional list of records to update directly.
        """
        # Retrieve the custom field configuration from options
        custom_field_config = options.get(ExperimentEntryTags.SET_CUSTOM_FIELD_VALUE)

        if not custom_field_config:
            return

        if not records:
            if new_entry_protocol.eln_entry.data_type_name.lower().startswith(ELNSampleDetailModel.DATA_TYPE_NAME.lower()):
                records = self.exp_handler.get_step_models(new_entry_protocol, ELNSampleDetailModel)
            elif new_entry_protocol.eln_entry.data_type_name.lower().startswith(ELNExperimentDetailModel.DATA_TYPE_NAME.lower()):
                records = self.exp_handler.get_step_models(new_entry_protocol, ELNExperimentDetailModel)
            else:
                return

        # Parse the custom field configuration
        field_value_pairs = custom_field_config.split(";")
        field_values = {}
        for pair in field_value_pairs:
            if "=" in pair:
                field_name, value = pair.split("=", 1)
                field_name = field_name.strip()
                value = value.strip()
                field_values[field_name] = value

        for record in records:
            for field_name, value in field_values.items():
                record.set_field_value(field_name.strip(), value.strip())

    def update_entry_records(self, context: CustomGrabberContext, fields_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]]):
        """
        Updates data records across the given entries using the sample details if available.

        Args:
            context (CustomGrabberContext): The custom context containing entries and sample details.
            :param fields_by_entry_id:
        """
        eln_protocol = ElnExperimentProtocol(self.context.eln_experiment, self.context.user)

        # Iterate through created entries and update their records as needed
        for new_entry in context.created_entries:
            new_entry_protocol = ElnEntryStep(eln_protocol, new_entry)
            options = new_entry_protocol.get_options()

            # Retrieve relevant records if sample details are available
            records = context.created_sample_details_by_entry_id.get(new_entry.entry_id, [])

            # Update fields for phase/step if applicable
            self.set_fields_for_records(
                entry=new_entry,
                entry_protocol=new_entry_protocol,
                field_names=PHASE_STEP_FIELDS,
                title=context.title,
                records=records,
                entry_field_defs=fields_by_entry_id[new_entry.entry_id]
            )

            # Update sample type if the entry is tagged for it
            if ExperimentEntryTags.SET_SAMPLE_TYPE_ON_SAMPLE_DETAIL in options:
                self.set_sample_type_on_entry_records(
                    context=context,
                    new_entry_protocol=new_entry_protocol,
                    options=options,
                    records=records,
                    entry_field_defs=fields_by_entry_id[new_entry.entry_id]
                )

            # Update custom fields if applicable
            if ExperimentEntryTags.SET_CUSTOM_FIELD_VALUE in options:
                self.set_custom_field_on_entry_records(
                    new_entry_protocol=new_entry_protocol,
                    options=options,
                    records=records
                )

    def enforce_sample_count_limit(
            self, protocol: ProtocolTemplateInfo, samples: Optional[List[SampleModel]], sample_entry: ProtocolStepType
    ) -> bool:
        """
        Checks if the sample count limit is respected for a given protocol.

        This method enforces a limit for protocols tagged with 'BUILDING_BLOCK_SAMPLE_LIMIT'.
        If the sample count exceeds the allowed limit (1), an error dialog is displayed,
        and the method returns False. Otherwise, it returns True.

        Args:
            protocol (ProtocolTemplateInfo): The protocol template information.
            samples (Optional[List[SampleModel]]): A list of sample models or None.
            sample_entry (ProtocolStepType): The protocol step entry to validate.

        Returns:
            bool: True if the sample count is within the limit or the limit is not applicable; False otherwise.
        """
        # Check if the protocol description contains the relevant tag
        has_sample_limit_tag = ProtocolTemplateTags.BUILDING_BLOCK_SAMPLE_LIMIT.lower() in protocol.description.lower()

        if has_sample_limit_tag and samples and len(samples) > 1:
            sample_name = sample_entry.get_name()
            self.callback.ok_dialog(
                "Error",
                f"This building block is designed to work with a single Sample only! \n\n"
                f"Please either reduce sample count in entry \"{sample_name}\" to 1 "
                "or pool samples to proceed."
            )
            return False

        return True

    def set_initial_load_values(self, context: CustomGrabberContext, fields_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]], sample_details: Dict[int, List[PyRecordModel]]):
        """
        Improved method to set initial load values, prioritizing data consistency and modularity.
        """
        created_entries = context.created_entries
        initial_load_sample_details = sample_details.get(created_entries[0].entry_id, [])
        source_samples = context.source_samples

        last_data_step = self.get_last_data_entry(context)

        if last_data_step:
            self.set_initial_load_values_using_data_entry(
                initial_load_records=initial_load_sample_details,
                last_data_step=last_data_step,
                fields_by_entry_id=fields_by_entry_id,
                initial_entry_id=created_entries[0].entry_id
            )
        elif source_samples:
            self.set_initial_load_values_using_source_samples(
                initial_load_records=initial_load_sample_details,
                source_samples=source_samples,
                fields_by_entry_id=fields_by_entry_id,
                initial_entry_id=created_entries[0].entry_id
            )

    def get_last_data_entry(self, context: CustomGrabberContext) -> Optional[ElnEntryStep]:
        """
        Retrieve the last data entry with specific tags.
        """
        created_ids = {entry.entry_id for entry in context.created_entries}
        all_steps = context.experiment_handler.get_all_steps()

        for step in all_steps:
            if step.get_id() in created_ids:
                continue

            options = step.get_options()
            if options.get(ExperimentEntryTags.PURIFICATION_PROTEIN_CAPTURE_FOR_YIELDS) == "Eluate":
                return step

        return None

    # List of fields to ignore during the copy process
    _fields_to_ignore = [
        "CreatedBy",
        "DataRecordName",
        "DataTypeId",
        "DateCreated",
        "OtherSampleId",
        "PhaseStep",
        "RecordId",
        "RelatedNotebookExperiment",
        "SampleId",
        "SampleType2",
        "VeloxLastModifiedBy",
        "VeloxLastModifiedDate"
    ]

    _field_mapping_eluate_to_initial_load = {
        "ConcA280A320Calc": "Concentration"
    }

    def set_initial_load_values_using_data_entry(self, initial_load_records: List[PyRecordModel], last_data_step: ElnEntryStep, fields_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]], initial_entry_id: int):
        """
        Enhanced method to populate initial load records using data from the last data entry.
        """
        last_data_records = self.exp_handler.get_step_models(last_data_step, ELNSampleDetailModel)
        sample_id_to_initial_record = {
            record.get_field_value("SampleId"): record for record in initial_load_records
        }

        initial_load_field_defs = {
            field_def.data_field_name for field_def in fields_by_entry_id.get(initial_entry_id, [])
        }

        last_data_fields = {
            field_def.data_field_name for field_def in fields_by_entry_id.get(last_data_step.eln_entry.entry_id, [])
        }

        for last_record in last_data_records:
            sample_id = last_record.get_field_value("SampleId")
            matching_initial_record = sample_id_to_initial_record.get(sample_id)

            if not matching_initial_record:
                continue

            for field_name in last_data_fields:
                dest_field = self._field_mapping_eluate_to_initial_load.get(field_name, field_name)

                if dest_field in initial_load_field_defs and field_name not in self._fields_to_ignore:
                    value = last_record.get_field_value(field_name)
                    matching_initial_record.set_field_value(dest_field, value)

    _sample_fields_to_initial_fields_mapping = {
        SampleModel.CONCENTRATION__FIELD_NAME.field_name: "Concentration",
        SampleModel.VOLUME__FIELD_NAME.field_name: "Volume"
    }

    def set_initial_load_values_using_source_samples(self, initial_load_records: List[PyRecordModel], source_samples: List[SampleModel], fields_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]], initial_entry_id: int):
        """
        Improved method to populate initial load values using source sample data.
        """
        sample_id_to_initial_record = {
            record.get_field_value("SampleId"): record for record in initial_load_records
        }

        initial_load_field_defs = {
            field_def.data_field_name for field_def in fields_by_entry_id.get(initial_entry_id, [])
        }

        for sample in source_samples:
            sample_id = sample.get_SampleId_field()
            matching_initial_record = sample_id_to_initial_record.get(sample_id)

            if not matching_initial_record:
                continue

            for sample_field, initial_field in self._sample_fields_to_initial_fields_mapping.items():
                if initial_field in initial_load_field_defs:
                    value = sample.get_field_value(sample_field)
                    matching_initial_record.set_field_value(initial_field, value)
