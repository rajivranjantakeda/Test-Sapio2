from decimal import Decimal
from typing import Dict, List, Set

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.eln.plate_designer import PlateDesignerEntry
from sapiopycommons.general.exceptions import SapioCriticalErrorException, SapioUserCancelledException, \
    SapioUserErrorException
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.eln.ExperimentEntry import ExperimentEntry
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import WrappedType
from sapiopylib.rest.utils.recordmodel.properties import Child

from sapio.enum.pick_list import PassFailValues
from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import ELNExperimentDetailModel, PlateDesignerWellElementModel, PlateModel, \
    C_DilutedSampleModel, SampleModel, C_ControlModel, ELNSampleDetailModel, C_DilutedControlModel
from sapio.model.eln_classes import ELNExperimentDetail
from sapio.webhook.elisa.elisa_entries import SampleDilution, SampleDilutionTargets
from sapio.webhook.elisa.softmax import SoftmaxGenerator


class GenerateSoftmaxOutput(CommonsWebhookHandler):
    """ An ELN entry toolbar button for a 3D Plating entry in the ELISA workflow. Based on the Plate Designer Well e
    Element records, this will generate a softmax output for the plate. """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Setup plate designer utility.
        plate_assignments_step = self.exp_handler.get_step("Plate Assignments")
        plating_entry: PlateDesignerEntry = PlateDesignerEntry(plate_assignments_step, self.exp_handler)

        # Grab all the source data.
        plates: List[PlateModel] = plating_entry.get_plates(PlateModel)

        # Group the source data by plate for reference.
        well_elements_by_plate: Dict[int, List[PlateDesignerWellElementModel]] = self.get_well_elements_by_plate(plating_entry)
        diluted_samples_by_plate: Dict[int, List[C_DilutedSampleModel]] = self.get_diluted_samples_by_plate(plating_entry)
        diluted_controls_by_plate: Dict[int, List[C_DilutedControlModel]] = self.get_diluted_controls_by_plate(plating_entry)

        # Generate the softmax output for each plate.
        generator = SoftmaxGenerator(context)
        files_to_create: Dict[str, bytes] = dict()
        for plate in plates:
            # Get the well elements for this plate.
            well_elements = well_elements_by_plate.get(plate.record_id)
            if well_elements is None:
                continue

            # Grab the source records.
            diluted_samples: List[C_DilutedSampleModel] = diluted_samples_by_plate.get(plate.record_id)
            diluted_controls: List[C_DilutedControlModel] = diluted_controls_by_plate.get(plate.record_id)

            # Generate the softmax output.
            file_details: (str, bytes) = generator.generate_file(plate, well_elements, diluted_samples, diluted_controls)
            files_to_create[file_details[0]] = file_details[1]

        # Send the files to the user.
        callback: CallbackUtil = CallbackUtil(context)
        for name, file_bytes in files_to_create.items():
            callback.write_file(name, file_bytes)

        return SapioWebhookResult(True, "Success!")

    def get_well_elements_by_plate(self, plate_designer_entry: PlateDesignerEntry) -> Dict[int, List[PlateDesignerWellElementModel]]:
        """ Group the well elements by plate. """
        # Get the source data.
        well_elements: List[PlateDesignerWellElementModel] = plate_designer_entry.get_plate_designer_well_elements(PlateDesignerWellElementModel)
        # Return the mapping.
        return self.rec_handler.map_by_field(well_elements, PlateDesignerWellElementModel.PLATERECORDID__FIELD_NAME.field_name)

    def get_sources_alt(self, plating_entry: PlateDesignerEntry, model_type: type[WrappedType]):
        # TODO: The current implementation of get sources relies on dependencies instead of grabbing sources based
        #  on the well elements. This is an alternate implementation. If the get_sources method changes, then we should
        #  update calls to this method to use the new implementation instead.
        well_elements: List[PlateDesignerWellElementModel] = plating_entry.get_plate_designer_well_elements(PlateDesignerWellElementModel)
        well_elements_for_type = [element for element in well_elements if element.get_SourceDataTypeName_field() == model_type.get_wrapper_data_type_name()]
        source_ids = [element.get_SourceRecordId_field() for element in well_elements_for_type]
        return self.rec_handler.query_models_by_id(model_type, source_ids)

    def get_diluted_samples_by_plate(self, plate_designer_entry: PlateDesignerEntry):
        """ Groups the diluted samples by their assigned plates record id. """
        # Get the source data.
        diluted_samples: List[C_DilutedSampleModel] = self.get_sources_alt(plate_designer_entry, C_DilutedSampleModel)
        well_elements: List[PlateDesignerWellElementModel] = plate_designer_entry.get_plate_designer_well_elements(PlateDesignerWellElementModel)

        # Group the diluted samples by plate.
        diluted_samples_by_plate: Dict[int, List[C_DilutedSampleModel]] = dict()
        diluted_samples_by_record_id: Dict[int, C_DilutedSampleModel] = self.rec_handler.map_by_id(diluted_samples)
        for element in well_elements:
            if element.get_SourceDataTypeName_field() == C_DilutedSampleModel.DATA_TYPE_NAME:
                diluted_sample = diluted_samples_by_record_id.get(element.get_SourceRecordId_field())
                diluted_samples_by_plate.setdefault(element.get_PlateRecordId_field(), list()).append(diluted_sample)
        return diluted_samples_by_plate

    def get_diluted_controls_by_plate(self, plating_entry: PlateDesignerEntry):
        # Get the source data
        diluted_controls: List[C_DilutedControlModel] = self.get_sources_alt(plating_entry, C_DilutedControlModel)
        well_elements: List[PlateDesignerWellElementModel] = plating_entry.get_plate_designer_well_elements(PlateDesignerWellElementModel)

        # Create the mapping between plate record id and diluted control.
        diluted_controls_by_plate: Dict[int, List[C_DilutedControlModel]] = dict()
        diluted_controls_by_record_id: Dict[int, C_DilutedControlModel] = self.rec_handler.map_by_id(diluted_controls)
        for element in well_elements:
            if element.get_SourceDataTypeName_field() == C_DilutedControlModel.DATA_TYPE_NAME:
                diluted_control = diluted_controls_by_record_id.get(element.get_SourceRecordId_field())
                diluted_controls_by_plate.setdefault(element.get_PlateRecordId_field(), list()).append(diluted_control)
        return diluted_controls_by_plate


class ExperimentPassFailPrompt(CommonsWebhookHandler):
    """
    Expected to run on an experiment details entry representing ELISA details. This will prompt the user with the fields
    for "Pass/Fail" and "Pass/Fail" comment.

    TODO: Should be moved into generic test aliquot/Assay section categorization-wise.
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Get the current steps field definitions.
        assay_details = self.exp_handler.get_step_by_option(ExperimentEntryTags.ASSAY_DETAILS)
        entry_with_field_defs = self.context.eln_manager.get_experiment_entry(context.eln_experiment.notebook_experiment_id, assay_details.eln_entry.entry_id, True)

        # Get the field definitions from that entry for "PassFail" and "Comment".
        pass_fail_field = None
        comment_field = None
        for field in entry_with_field_defs.field_definition_list:
            if field.data_field_name == ELNExperimentDetail.PASS_FAIL:
                pass_fail_field = field
            if field.data_field_name == ELNExperimentDetail.COMMENT:
                comment_field = field
            if pass_fail_field is not None and comment_field is not None:
                break

        # Handle when they aren't found.
        if pass_fail_field is None or comment_field is None:
            return SapioWebhookResult(False, "Pass/Fail fields have not been configured correctly."
                                      + " Please contact a system administrator.")

        # Get the experiment detail record.
        detail_model: ELNExperimentDetailModel = self.exp_handler.get_step_models(assay_details, ELNExperimentDetailModel).pop()

        # Show the form dialog.
        callback: CallbackUtil = CallbackUtil(context)
        callback.set_dialog_width(width_percent=5)

        # Set fields to editable and compile default values.
        pass_fail_field.editable = True
        comment_field.editable = True
        comment_default = detail_model.get_field_value(ELNExperimentDetail.COMMENT)
        pass_fail_default = self.get_pass_fail_default()
        default_values = {
            ELNExperimentDetail.PASS_FAIL: pass_fail_default,
            ELNExperimentDetail.COMMENT: comment_default
        }

        # Prompt the user, and handle the cancellation by rejection the transaction.
        values = dict()
        try:
            values: Dict[str, str] = callback.form_dialog("Pass/Fail", "Please provide Pass/Fail Details", [pass_fail_field, comment_field], default_values)
        except SapioUserCancelledException:
            return SapioWebhookResult(False, "User cancelled the dialog.")

        # Use the values to set the fields on the experiment entry.
        pass_fail: str = values.get(ELNExperimentDetail.PASS_FAIL)
        comment: str = values.get(ELNExperimentDetail.COMMENT)

        # Set the fields on the entry.
        detail_model.set_field_value(ELNExperimentDetail.PASS_FAIL, pass_fail)
        detail_model.set_field_value(ELNExperimentDetail.COMMENT, comment)

        # Store and commit
        self.rec_man.store_and_commit()
        return SapioWebhookResult(True)

    def get_pass_fail_default(self):
        """
        Get the default value for the pass/fail field. If any of the suitability parameters are Fail, then return
        Fail. Otherwise, return pass.
        """
        suitability_details: List[ELNExperimentDetailModel] = self.exp_handler.get_step_models("System Suitability", ELNExperimentDetailModel)
        for detail in suitability_details:
            pass_fail = detail.get_field_value(ELNExperimentDetail.SUITABILITY_PASS_FAIL)
            if pass_fail == PassFailValues.FAIL:
                return PassFailValues.FAIL
        return PassFailValues.PASS


class CreatePreparedControls(CommonsWebhookHandler):
    """
    Run on submit of the ELISA Controls/Standards specification entry. For each row in that entry,
    Create a C_PreparedControl record and copy applicable values from the eln detail to the prepared control.
    Additionally, the new prepared control should be a child of the sample whose lot number was specified in the row.
    Then add them to the Standards entry.
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Get the Experiment details rows from the "Control / Standard Specification" entry.
        control_material_details: List[ELNExperimentDetailModel] = self.exp_handler.get_step_models("Control / Standard Specification", ELNExperimentDetailModel)

        # Query for the source samples, and map them by their lot number.
        samples_by_lot_by_type: Dict[str, Dict[str, SampleModel]] = self.get_samples_by_lot_number(control_material_details)

        # For each row in the control material details, create a prepared control.
        prepared_controls: List[C_DilutedControlModel] = list()
        for detail in control_material_details:
            # Get the lot number and type from the detail.
            lot_number = detail.get_field_value(ELNExperimentDetail.CONSUMABLE_LOT)
            consumable_type = detail.get_field_value(ELNExperimentDetail.CONSUMABLE_TYPE)
            # Get the sample with the lot number.
            sample = None
            samples_by_lot = samples_by_lot_by_type.get(consumable_type)
            if samples_by_lot is not None:
                sample = samples_by_lot.get(lot_number)
            # Create the prepared control.
            prepared_control: C_DilutedControlModel = self.create_prepared_control(sample, detail)
            prepared_controls.append(prepared_control)

        # Delete existing records.
        existing_standards: List[C_DilutedControlModel] = self.exp_handler.get_step_models("Standards", C_DilutedControlModel)
        for existing_standard in existing_standards:
            existing_standard.delete()

        # Store the prepared controls.
        self.rec_man.store_and_commit()

        # Add them to the standards entry.
        self.exp_handler.set_step_records("Standards", prepared_controls)

        # All done.
        return SapioWebhookResult(True)

    def create_prepared_control(self, sample: SampleModel, eln_row: ELNExperimentDetailModel) -> C_DilutedControlModel:
        """
        Creates the prepared control model (C_Diluted_Control) based on the eln row. If the sample model is provided,
        then the prepared control will be created as a child of that sample. Otherwise, the prepared control will be
        created in an orphaned state.
        """
        # Create the prepared control.
        prepared_control: None | C_DilutedControlModel = None
        if sample is None:
            prepared_control = self.inst_man.add_new_record_of_type(C_DilutedControlModel)
        else:
            prepared_control: C_DilutedControlModel = sample.add(Child.create(C_DilutedControlModel))

        # Classification
        classification = eln_row.get_field_value(ELNExperimentDetail.CONSUMABLE_CLASSIFICATION)
        prepared_control.set_C_ConsumableClassification_field(classification)

        # Group Type
        group_type = eln_row.get_field_value(C_DilutedControlModel.C_SOFTMAXGROUPTYPE__FIELD_NAME.field_name)
        if group_type:
            prepared_control.set_C_SoftmaxGroupType_field(group_type)

        # Control Type
        control_type = eln_row.get_field_value(ELNExperimentDetail.CONSUMABLE_TYPE)
        prepared_control.set_C_ConsumableType_field(control_type)

        # Lot number
        lot = eln_row.get_field_value(ELNExperimentDetail.CONSUMABLE_LOT)
        prepared_control.set_C_LotNumber_field(lot)

        # Concentration
        concentration = eln_row.get_field_value(ELNExperimentDetail.TARGET_CONCENTRATION)
        prepared_control.set_C_Concentration_field(concentration)

        # Concentration Units
        concentration_units = eln_row.get_field_value(ELNExperimentDetail.TARGET_CONCENTRATION_UNITS)
        prepared_control.set_C_ConcentrationUnits_field(concentration_units)

        return prepared_control

    def get_samples_by_lot_number(self, control_material_details: List[ELNExperimentDetailModel]) -> Dict[str, Dict[str, SampleModel]]:
        """
        Collects the lot-numbers, and queries for sample wit those lot numbers. Excludes blank lot numbers.
        """
        # Get the lot numbers from the control material details.
        lot_numbers: List[str] = list()
        for detail in control_material_details:
            lot_number = detail.get_field_value(ELNExperimentDetail.CONSUMABLE_LOT)
            # Exclude blank and "None" lot numbers.
            if lot_number is not None and lot_number.strip() != "":
                lot_numbers.append(lot_number)

        # Query for the samples with the lot-numbers.
        samples: List[SampleModel] = self.rec_handler.query_models(SampleModel, SampleModel.C_LOT__FIELD_NAME, lot_numbers)

        # Map the samples by their lot number and by sample type.
        samples_by_lot_by_type: Dict[str, Dict[str, SampleModel]] = dict()
        for sample in samples:
            lot = sample.get_C_Lot_field()
            sample_type = sample.get_field_value("C_Control.C_ConsumableType")
            samples_by_lot_by_type.setdefault(sample_type, dict())
            lot_map = samples_by_lot_by_type.get(sample_type)
            lot_map[lot] = sample
        return samples_by_lot_by_type


class SampleDilutionTargetsPrompt(CommonsWebhookHandler):
    """
    Run on initialization of the Sample Dilution Targets entry. Prompts the user for a number of dilutions, and
    prepopulates the table with one row per dilution per sample.
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Prompt the user with an integer input for number of dilutions.
        callback: CallbackUtil = CallbackUtil(context)
        callback.set_dialog_width(width_percent=5)

        number_of_dilutions = callback.integer_input_dialog("Dilution Targets",
                                                            "How Many Dilutions would you like to perform?",
                                                            "DilutionTargets",
                                                            1,
                                                            0)

        # Get the sample models from the samples entry.
        samples: List[SampleModel] = self.exp_handler.get_step_models("Samples", SampleModel)

        # Grab the existing sample details and delete them to simplify the logic.
        targets_entry: ElnEntryStep = self.exp_handler.get_step("Sample Dilution Targets")
        sample_details: List[ELNSampleDetailModel] = self.exp_handler.get_step_models(targets_entry, ELNSampleDetailModel)
        for x in sample_details:
            x.delete()

        # Create a row for each sample and dilution.
        for sample in samples:
            for i in range(number_of_dilutions):
                sample_detail: ELNSampleDetailModel = self.exp_handler.add_sample_details(targets_entry, [sample], ELNSampleDetailModel).pop()
                sample_detail.set_field_value(SampleDilutionTargets.DILUTION_NUMBER, i + 1)

        # Store and commit.
        self.rec_man.store_and_commit()
        return SapioWebhookResult(True)


class PopulateDilutionDetails(CommonsWebhookHandler):
    """
    Runs on Completion of the Sample Dilution entry. This will populate the dilution details for each sample.
    There will be two sample detail records for each samples dilution target.
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Get the dilution targets and the current samples.
        dilution_targets: List[ELNSampleDetailModel] = self.exp_handler.get_step_models("Sample Dilution Targets", ELNSampleDetailModel)
        samples: List[SampleModel] = self.exp_handler.get_step_models("Samples", SampleModel)
        samples_by_id: Dict[str, SampleModel] = self.rec_handler.map_by_unique_field(samples, SampleModel.SAMPLEID__FIELD_NAME.field_name)

        # Group dilution targets by sample_id to calculate counts.
        sample_to_dilution_factors: Dict[str, List[Decimal]] = {}
        for dilution_target in dilution_targets:
            sample_id = dilution_target.get_SampleId_field()
            target_dilution_factor = dilution_target.get_field_value(SampleDilutionTargets.TARGET_DILUTION_FACTOR)
            if sample_id not in sample_to_dilution_factors:
                sample_to_dilution_factors[sample_id] = []
            sample_to_dilution_factors[sample_id].append(target_dilution_factor)

        # Delete any existing records in the Sample Dilution entry.
        existing_details = self.exp_handler.get_step_models("Sample Dilution", ELNSampleDetailModel)
        for existing_detail in existing_details:
            existing_detail.delete()

        # Iterate over samples and create the appropriate rows.
        sample_dilution_step: ElnEntryStep = self.exp_handler.get_step("Sample Dilution")
        for sample_id, dilution_factors in sample_to_dilution_factors.items():
            sample = samples_by_id.get(sample_id)
            num_dilution_factors = len(dilution_factors)

            # Create records. First records without dilution factors, last records with them.
            total_records_to_create = num_dilution_factors * 2
            for i in range(total_records_to_create):
                dilution_detail: ELNSampleDetailModel = self.exp_handler.add_sample_details(sample_dilution_step, [sample], ELNSampleDetailModel).pop()
                # dilution_detail.set_field_value(SampleDilution.SAMPLE_VOLUME, sample.get_Volume_field())

                # Add dilution factors only in the last `num_dilution_factors` rows.
                if i >= total_records_to_create - num_dilution_factors:
                    index_in_factors = i - (total_records_to_create - num_dilution_factors)

                    # Final dilution factor is a calculated field now, so we can't set it. Keeping this logic just in
                    # case we need to do this later though
                    # dilution_detail.set_field_value(SampleDilution.FINAL_DILUTION_FACTOR, dilution_factors[index_in_factors])

        # Store and commit.
        self.rec_man.store_and_commit()
        return SapioWebhookResult(True)


class CreateDilutedSamples(CommonsWebhookHandler):
    """
    Creates global "C_DilutedSample" records based on the sample details within the "Sample Dilution Targets" and
    "Sample Dilution" entries.
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Mark the existing records for deletion, in case we are resubmitting.
        existing_diluted_sample_records: List[C_DilutedSampleModel] = self.exp_handler.get_step_models("Diluted Samples", C_DilutedSampleModel)
        for existing_record in existing_diluted_sample_records:
            existing_record.delete()

        # Get the sample details from the sample dilution entry.
        dilution_targets: List[ELNSampleDetailModel] = self.exp_handler.get_step_models("Sample Dilution Targets", ELNSampleDetailModel)

        # Make the sample dilution details available by sample id.
        dilution_instructions: List[ELNSampleDetailModel] = self.exp_handler.get_step_models("Sample Dilution", ELNSampleDetailModel)
        dilution_instructions_by_sample_id: Dict[str, List[ELNSampleDetailModel]] = self.rec_handler.map_by_field(dilution_instructions, ELNSampleDetailModel.SAMPLEID__FIELD_NAME.field_name)

        # Get the source samples as well.
        samples: List[SampleModel] = self.exp_handler.get_step_models("Samples", SampleModel)
        samples_by_id: Dict[str, SampleModel] = self.rec_handler.map_by_unique_field(samples, SampleModel.SAMPLEID__FIELD_NAME.field_name)

        # Start making dilution details.
        diluted_samples: List[C_DilutedSampleModel] = list()
        for dilution_target in dilution_targets:

            # Grab the source sample.
            source_sample: SampleModel = samples_by_id.get(dilution_target.get_SampleId_field())
            if source_sample is None:
                raise SapioCriticalErrorException("Could not find source sample for sample dilution with sample id: " + dilution_target.get_SampleId_field())

            # Target Dilution Factor.
            target_dilution_factor = dilution_target.get_field_value(SampleDilutionTargets.TARGET_DILUTION_FACTOR)

            # Grab the sample dilution with a matching dilution factor.
            dilution_instructions: List[ELNSampleDetailModel] = dilution_instructions_by_sample_id.get(dilution_target.get_SampleId_field())
            if dilution_instructions is None or not dilution_instructions:
                raise SapioCriticalErrorException("Could not find dilution instructions for sample id: " + dilution_target.get_SampleId_field())

            # Grab the dilution which matches the target dilution factor.
            last_dilution = None
            for dilution_instruction in dilution_instructions:
                if dilution_instruction.get_field_value(SampleDilution.FINAL_DILUTION_FACTOR) == target_dilution_factor:
                    last_dilution = dilution_instruction
                    break

            # Create a diluted sample for each of the original dilution targets.
            diluted_sample: C_DilutedSampleModel = source_sample.add(Child.create(C_DilutedSampleModel))
            diluted_sample.set_C_SampleId_field(dilution_target.get_SampleId_field())
            diluted_sample.set_C_ExemplarSampleType_field(source_sample.get_ExemplarSampleType_field())
            if last_dilution is not None:
                diluted_sample.set_C_Volume_field(last_dilution.get_field_value(SampleDilution.TOTAL_VOLUME))
            diluted_sample.set_C_DilutionFactor_field(target_dilution_factor)
            diluted_sample.set_C_DilutionNumber_field(dilution_target.get_field_value(SampleDilutionTargets.DILUTION_NUMBER))
            diluted_sample.set_C_VolumeUnits_field("uL")

            # Sample name = [Sample ID] + "(DF + [Target Dilution Factor])" + "K)"
            dilution_factor = dilution_target.get_field_value(SampleDilutionTargets.TARGET_DILUTION_FACTOR)
            if dilution_factor is not None:
                if dilution_factor >= 1000:
                    target_dilution_factor = f"{int(dilution_factor / 1000)}K"
                else:
                    target_dilution_factor = f"{int(dilution_factor)}"
                sample_name = f"{source_sample.get_SampleId_field()} (DF {target_dilution_factor})"
            else:
                sample_name = source_sample.get_SampleId_field()
            diluted_sample.set_C_OtherSampleId_field(sample_name)
            diluted_samples.append(diluted_sample)

        # Store and commit, so that the records exist. Then add them to this entry.
        self.rec_man.store_and_commit()
        self.exp_handler.set_step_records("Diluted Samples", diluted_samples)

        return SapioWebhookResult(True)


class CheckForDuplicateSamples(CommonsWebhookHandler):
    """
    Checks for duplicate diluted samples in Diluted Samples entry.
    Raises a SapioCriticalErrorException if duplicates are found.
    """
    def execute(self, context):
        # Get the samples from the Diluted Samples entry.
        diluted_samples: List[C_DilutedSampleModel] = self.exp_handler.get_step_models("Diluted Samples", C_DilutedSampleModel)

        # Get the names of the diluted samples.
        diluted_samples_names: list[str] = [sample.get_C_OtherSampleId_field() for sample in diluted_samples]

        # Check for duplicates.
        if len(diluted_samples_names) != len(set(diluted_samples_names)):
            raise SapioCriticalErrorException("Duplicate diluted samples were created. This is not allowed.")

        return SapioWebhookResult(True)
