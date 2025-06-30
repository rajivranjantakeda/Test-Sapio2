from typing import List, Dict

from sapiopycommons.general.exceptions import SapioUserErrorException
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep
from sapiopylib.rest.utils.recordmodel.RelationshipPath import RelationshipPath

from sapio.enum.pick_list import PassFailValues, TestAliquotStatuses
from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import ELNSampleDetailModel, SampleModel, C_TestAliquotModel, ELNExperimentDetailModel
from sapio.model.eln_classes import ELNExperimentDetail
from sapio.webhook.hplc.entries import SampleDataFields
from sapio.webhook.test_aliquot.designation import DesignationManager


DESIGNATION_UNITS: Dict[str, str] = {
    "HPLC/UPLC": "mg/mL",
    "ELISA": "ng/mL"
}

DESIGNATION_CONC_FIELD: Dict[str, str] = {
    "HPLC/UPLC": "ConcentrationmgmL",
    "ELISA": "AvgI2SngmL"
}


class CopyAssayResults(CommonsWebhookHandler):
    """
    This Webhook will gather the sample details from the "Sample Data" entry, match them to the sample record in the
    Samples entry, and copy the concentration value from the sample detail record to the samples Sample Grandparent.
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Get the assay details step and the assay details model.
        assay_step: ElnEntryStep = self.exp_handler.get_step_by_option(ExperimentEntryTags.ASSAY_DETAILS)
        assay_detail: ELNExperimentDetailModel = self.exp_handler.get_step_models(assay_step, ELNExperimentDetailModel).pop()
        pass_str_value: str | None = assay_detail.get_field_value(ELNExperimentDetail.PASS_FAIL)
        if pass_str_value is None:
            return SapioWebhookResult(False, "The assay details entry does not have a pass/fail value.")

        if pass_str_value == PassFailValues.PASS:
            self.pass_results()
        elif pass_str_value == PassFailValues.FAIL:
            self.fail_results()
        else:
            raise SapioUserErrorException("The pass/fail value for the assay details entry is not recognized. Please contact a system administrator.")

        # All done.
        self.rec_man.store_and_commit()
        return SapioWebhookResult(True)

    def pass_results(self):
        # Grab the sample details.
        assay_results_step = self.exp_handler.get_step_by_option(ExperimentEntryTags.ASSAY_RESULTS)
        sample_details: List[ELNSampleDetailModel] = self.exp_handler.get_step_models(assay_results_step,
                                                                                      ELNSampleDetailModel)

        # Grab the sample records. Map by sample ID.
        samples: List[SampleModel] = self.exp_handler.get_step_models("Samples", SampleModel)
        samples_by_sample_id: Dict[str, SampleModel] = self.rec_handler.map_by_unique_field(samples,
                                                                                            SampleModel.SAMPLEID__FIELD_NAME)

        # Load the path to the samples parent test-aliquots and the test-aliquots sample parents.
        path_to_source_sample: RelationshipPath = (RelationshipPath()
                                                   .reverse_type(C_TestAliquotModel, C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name)
                                                   .parent_type(SampleModel))
        self.rel_man.load_path_of_type(samples, path_to_source_sample)
        source_samples: Dict[SampleModel, SampleModel] = self.map_to_sources(samples)

        # Add enforcement to make sure that all the source samples are distinct.
        self.enforce_unique_sources(source_samples)

        # Prepare designation related information.
        # TODO: Could this be done using the already loaded test aliquots to remove a webservice call?
        designation = DesignationManager(self.context).get_designation(self.context.eln_experiment.template_id)
        conc_field_name: str = self.get_conc_field_name(designation)
        units = self.get_assay_units(designation)
        # iterate over the sample details, grab the matched sample. Then get the samples grandparent sample, and copy
        # The concentration value.
        for sample_data in sample_details:
            # Get the sample details related sample record.
            sample_id = sample_data.get_SampleId_field()
            sample: SampleModel = samples_by_sample_id.get(sample_id)
            if sample is None:
                raise SapioUserErrorException(
                    "The result data for sample ID '" + sample_id + "' does not have a source sample in this experiment.")

            # Get the test aliquot.
            test_aliquots: List[C_TestAliquotModel] = sample.get_reverse_side_link(C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name, C_TestAliquotModel)
            if len(test_aliquots) < 1:
                raise SapioUserErrorException("The sample with Sample ID: '" + sample_id + "' does not have a test aliquot. Please contact a system administrator.")
            test_aliquot: C_TestAliquotModel = test_aliquots.pop()
            test_aliquot.set_C_Status_field(TestAliquotStatuses.PASS)

            # Get the source sample.
            source_sample: SampleModel = source_samples.get(sample)
            if source_sample is None:
                raise SapioUserErrorException(
                    "The original source sample for the sample with Sample ID: '" + sample_id + "' could not be found. Please contact a system administrator.")

            # Set the samples concentration. Also set update the Test Aliquot status.
            concentration = sample_data.get_field_value(conc_field_name)
            source_sample.set_Concentration_field(concentration)
            source_sample.set_ConcentrationUnits_field(units)

    def get_assay_units(self, designation: str):
        """
        Retrieves the designation for the template, and then returns the units for that designation.

        :returns: The concentration units to be used on the source sample based on the designated assay.
        """
        units = DESIGNATION_UNITS.get(designation)
        if units is not None:
            return units
        raise SapioUserErrorException("The designation for this experiment is not recognized. Please contact a system administrator.")

    def enforce_unique_sources(self, source_samples: Dict[SampleModel, SampleModel]):
        """
        Given the dictionary of samples in the experiment to the source samples, ensure that all of the source
        samples are unique. Raises a sapio user error exception if there are duplicates.

        :param source_samples: The dictionary of samples in the experiment to the source samples.
        :returns: None
        """
        unique_source_samples = set()
        for source_sample in source_samples.values():
            if source_sample in unique_source_samples:
                raise SapioUserErrorException("There are duplicate source samples in the experiment. "
                                              + "Please contact a system administrator.")
            unique_source_samples.add(source_sample)

    def fail_results(self):
        """
        Marks all the test aliquots for samples in the experiment as failed.
        """
        # Grab the sample records. Map by sample ID.
        samples: List[SampleModel] = self.exp_handler.get_step_models("Samples", SampleModel)

        # Load and get the test aliquots.
        self.rel_man.load_reverse_side_links_of_type(samples, C_TestAliquotModel, C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name)
        for sample in samples:
            test_aliquot: List[C_TestAliquotModel] = sample.get_reverse_side_link(C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name, C_TestAliquotModel)
            if len(test_aliquot) < 0:
                continue
            for aliquot in test_aliquot:
                aliquot.set_C_Status_field(TestAliquotStatuses.FAIL)

    def map_to_sources(self, samples: List[SampleModel]):
        """
        Maps the samples to the grandparent source samples, which are parents of the reverse side linked test aliquots.
        TODO: This can be replaced with record_handler.get_linear_path() after the next sapiopycommons release.
        """
        result: Dict[SampleModel, SampleModel] = dict()
        for sample in samples:
            # Get the test aliquot.
            test_aliquot = sample.get_reverse_side_link(C_TestAliquotModel.C_ALIQUOTSAMPLE__FIELD_NAME.field_name, C_TestAliquotModel)
            if test_aliquot is None or len(test_aliquot) < 1:
                continue

            # Get the source sample.
            source_sample = test_aliquot.pop().get_parent_of_type(SampleModel)
            result[sample] = source_sample

        return result

    def get_conc_field_name(self, designation: str):
        return DESIGNATION_CONC_FIELD.get(designation)
