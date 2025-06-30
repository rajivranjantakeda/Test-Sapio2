import decimal

from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.recordmodel.properties import Child

from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import C_StepYieldModel, C_PurificationYieldConfigModel, SampleModel, ELNSampleDetailModel


class LoadPurificationYields(CommonsWebhookHandler):
    """
    This class handles the loading and processing of purification yields in a step-based experimental workflow.
    It calculates step yields, verifies yield ranges, and updates relevant records.
    """

    ELUATE_OPTION_VALUE = "Eluate"
    STEP_YIELDS_LABEL = "Step Yields"
    TOTAL_PROTEIN_FIELD = "TotalProtein"
    SAMPLE_TYPE_FIELD = "SampleType2"

    @staticmethod
    def is_yield_in_range(total_protein_eluate, total_protein_load, matching_config):
        """
        Checks if the calculated yield is within the configured range and returns a descriptive string.

        Args:
            total_protein_eluate (float): Total protein in the eluate.
            total_protein_load (float): Total protein in the load.
            matching_config (C_PurificationYieldConfigModel): Yield configuration for the phase.

        Returns:
            str: "In Range", "Below Range", or "Above Range" based on the calculated yield.
        """
        min_yield = matching_config.get_C_MinYieldRange_field()
        max_yield = matching_config.get_C_MaxYieldRange_field()
        step_yield = (total_protein_eluate / total_protein_load) * 100

        if step_yield < min_yield:
            return "Below Range"
        elif step_yield > max_yield:
            return "Above Range"
        else:
            return "In Range"

    @staticmethod
    def get_matching_config(yield_configs, phase):
        """
        Retrieves the yield configuration matching the given phase.

        Args:
            yield_configs (list): List of yield configuration models.
            phase (str): The phase of the experiment.

        Returns:
            C_PurificationYieldConfigModel: The matching configuration model.

        Raises:
            ValueError: If no matching configuration is found.
        """
        matching_config = next((config for config in yield_configs if config.get_C_PhaseStep_field() == phase), None)
        if not matching_config:
            raise ValueError(f"No matching PurificationYieldConfigModel found for phase: {phase}")
        return matching_config

    @staticmethod
    def set_step_yield_values(step_yield, total_protein_load, total_protein_eluate, sample_type_load, sample_type_eluate, phase, matching_config):
        """
        Sets the values for a step yield record.

        Args:
            step_yield (C_StepYieldModel): The step yield model to update.
            total_protein_load (float): Total protein in the load.
            total_protein_eluate (float): Total protein in the eluate.
            sample_type_load (str): Sample type for the load.
            sample_type_eluate (str): Sample type for the eluate.
            phase (str): The phase of the experiment.
            matching_config (C_PurificationYieldConfigModel): Yield configuration for the phase.

        Returns:
            C_StepYieldModel: The updated step yield model.
        """
        step_yield.set_C_TotalLoadProteinmg_field(total_protein_load)
        step_yield.set_C_TotalEluateProteinmg_field(total_protein_eluate)
        step_yield.set_C_StepYield_field((total_protein_eluate / total_protein_load) * 100)
        step_yield.set_C_EluateSampleType_field(sample_type_eluate)
        step_yield.set_C_LoadSampleType_field(sample_type_load)
        step_yield.set_C_Step_field(phase)
        step_yield.set_C_MinYieldRange_field(matching_config.get_C_MinYieldRange_field())
        step_yield.set_C_MaxYieldRange_field(matching_config.get_C_MaxYieldRange_field())
        step_yield.set_C_IsYieldInRange_field(LoadPurificationYields.is_yield_in_range(total_protein_eluate, total_protein_load, matching_config))
        return step_yield

    def process_steps(self, all_steps: list, yield_configs: list) -> list:
        """
        Processes the experimental steps to calculate and update yields.

        Args:
            all_steps (list): List of all steps in the experiment.
            yield_configs (list): List of yield configuration models.

        Returns:
            list: Updated step yield records.

        Raises:
            ValueError: If an expected step record is missing or invalid.
        """
        source_sample: SampleModel = None
        old_yields = self.exp_handler.get_step_models(self.STEP_YIELDS_LABEL, C_StepYieldModel)
        step_yields = []
        count = 0

        load_total_protein, load_sample_type = 0, ""
        looking_for_eluate = False

        for step in all_steps:

            sample_details = self.get_sample_details(step)
            sample_detail = self.validate_sample_details(sample_details)

            if not looking_for_eluate:
                load_total_protein, load_sample_type = self.extract_sample_data(sample_detail)
                looking_for_eluate = True
                continue

            if self.is_result_eluate_step(step):
                step_yield = self.process_eluate_step(
                    step, sample_detail, old_yields, count, source_sample, yield_configs, load_total_protein, load_sample_type
                )

                if step_yield is None:
                    continue

                step_yields.append(step_yield)
                load_total_protein, load_sample_type = self.extract_sample_data(sample_detail)
                count += 1
            else:
                load_total_protein, load_sample_type = self.extract_sample_data(sample_detail)

        self.delete_remaining_yields(old_yields, count)
        return step_yields

    def get_sample_details(self, step) -> list:
        """
        Fetches sample details for a given step.
        """
        return self.exp_handler.get_step_models(step, ELNSampleDetailModel)

    def validate_sample_details(self, sample_details: list) -> ELNSampleDetailModel:
        """
        Validates that exactly one sample detail exists.
        """
        if len(sample_details) != 1:
            raise ValueError("Expected exactly one record in the load step.")
        return sample_details[0]

    def extract_sample_data(self, sample_detail: ELNSampleDetailModel) -> tuple:
        """
        Extracts and returns total protein and sample type from a sample detail.
        """
        return (
            sample_detail.get_field_value(self.TOTAL_PROTEIN_FIELD),
            sample_detail.get_field_value(self.SAMPLE_TYPE_FIELD),
        )

    def process_eluate_step(self, step, sample_detail, old_yields, count, source_sample, yield_configs, load_total_protein, load_sample_type):
        """
        Processes an eluate step and returns the updated step yield.
        """
        eluate_total_protein, eluate_sample_type = self.extract_sample_data(sample_detail)

        # Check if either total_protein_load or total_protein_eluate is None or 0
        if not load_total_protein or not eluate_total_protein:
            return None

        phase = self.exp_handler.get_step_option(step, ExperimentEntryTags.PHASE_STEP)
        matching_config = self.get_matching_config(yield_configs, phase)

        if source_sample is None:
            self.rel_man.load_parents_of_type([sample_detail], SampleModel)
            source_sample = sample_detail.get_parent_of_type(SampleModel)

        step_yield = old_yields[count] if count < len(old_yields) else source_sample.add(Child.create(C_StepYieldModel))
        return self.set_step_yield_values(
            step_yield, load_total_protein, eluate_total_protein, load_sample_type, eluate_sample_type, phase, matching_config
        )

    def delete_remaining_yields(self, old_yields, start_index: int):
        """
        Deletes remaining old yield records starting from the given index.
        """
        for old_yield in old_yields[start_index:]:
            old_yield.delete()

    def is_result_eluate_step(self, step):
        """
        Checks if a step is an eluate step.

        Args:
            step: The experimental step to check.

        Returns:
            bool: True if the step is an eluate step, False otherwise.
        """
        return self.exp_handler.get_step_option(step, ExperimentEntryTags.PURIFICATION_PROTEIN_CAPTURE_FOR_YIELDS) == self.ELUATE_OPTION_VALUE

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        yield_configs = self.rec_handler.query_all_models(C_PurificationYieldConfigModel)
        all_steps = self.exp_handler.get_steps_by_option(ExperimentEntryTags.PURIFICATION_PROTEIN_CAPTURE_FOR_YIELDS)

        self.rec_man.store_and_commit()
        step_yields = self.process_steps(all_steps, yield_configs)

        self.rec_man.store_and_commit()
        self.exp_handler.set_step_records(self.STEP_YIELDS_LABEL, step_yields)

        return SapioWebhookResult(True)
