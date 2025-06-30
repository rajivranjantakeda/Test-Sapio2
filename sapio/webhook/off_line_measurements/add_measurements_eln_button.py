from typing import List

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.general.time_util import TimeUtil
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.ClientCallbackService import ClientCallback
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.eln.ExperimentEntry import ExperimentEntry
from sapiopylib.rest.pojo.eln.SapioELNEnums import ExperimentEntryStatus
from sapiopylib.rest.pojo.webhook.ClientCallbackRequest import DisplayPopupRequest, PopupType
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep, ElnExperimentProtocol
from sapiopylib.rest.utils.recordmodel.properties import Child

from sapio.enum.Instrument_type import InstrumentType
from sapio.enum.tags import ExperimentEntryTags
from sapio.model.data_type_models import C_CellCultureOnLineMeasurementModel, SampleModel, ELNExperimentDetailModel, C_CellCultureMeasurementsModel

INSTRUMENT_TRACKING = "Instrument Tracking"


class InstrumentTrackingDetail:
    """
    This class will store the string constants for Instrument Tracking fields referenced in this webhook.
    """
    INSTRUMENT_TYPE = "InstrumentType"
    INSTRUMENT_USED = "InstrumentUsed"


class AddMeasurementsButton(CommonsWebhookHandler):
    """
    This webhook is intended to be invoked from an ELN Entry Toolbar for Cell culture offline measurement, and create
    one offline measurement for every permutation of sample and "Cell Counter" instrument. The sample entry
    will be determined by the dependencies on the current entry, and the instrument tracking entry will be determined
    by the name 'Instrument Tracking'.

    Documentation Reference: https://onetakeda.atlassian.net/browse/ELNMSLAB-472
    """

    experiment_handler: ExperimentHandler
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # Initialize experiment handler.
        self.experiment_handler = ExperimentHandler(context)

        # Get the current experiment entry.
        measurements_entry: ExperimentEntry = context.experiment_entry

        # If the entry has already been submitted, return early.
        if measurements_entry.entry_status == ExperimentEntryStatus.Completed:
            warning = DisplayPopupRequest("Warning", "This entry has already been completed. No measurements have been added.", PopupType.Warning)
            ClientCallback(self.context.user).display_popup(warning)
            return SapioWebhookResult(True)

        # Get the samples based on the measurements entry.
        # If no samples are found, let the user know and return.
        samples: List[SampleModel] | None = self.get_samples(measurements_entry)
        if samples is None:
            CallbackUtil(self.context).ok_dialog("Error",
                                                 "This entry does not have it's dependencies configured properly. "
                                                 "Please contact a system administrator for assistance.")
            return SapioWebhookResult(True)

        # for each sample, and for each cell counter tracked, add a measurement for today.
        timestamp = TimeUtil.now_in_millis()
        phase_step: str = self.get_phase_step_from_entry(measurements_entry)
        new_measurements = self.create_measurements(samples, timestamp, phase_step)

        # Commit the records.
        self.rec_man.store_and_commit()

        # Add them to the entry.
        measurement_step = ElnEntryStep(ElnExperimentProtocol(context.eln_experiment, context.user), measurements_entry)
        self.experiment_handler.add_step_records(measurement_step, new_measurements)

        return SapioWebhookResult(True, eln_entry_refresh_list=[measurements_entry])

    def create_measurements(self, samples: List[SampleModel], timestamp: int, phase_step: str):
        """
        Creates Cell Culture offline meassurements for each permutation of sample and cell counter present, and
        using the given timestamp. The created measurements for a given sample will be related as children.

        :param cell_counter_details: The Instrument Tracking ELNExperimentDetailModels for each tracked Cell Counter.
        :param samples: The list of SampleModels representing the list of samples to create measurements for.
        :param timestamp: The timestamp to create all of the measurements with as an int.
        """
        callback = CallbackUtil(self.context)
        rows_to_create:int = callback.integer_input_dialog(
            title="Input Widget",
            msg="Please input the number of entries to create.",
            field_name="rowstocreate"
        )
        new_measurements = list()
        entry_name = self.context.active_step.get_name()
        for sample in samples:
            for index in range(rows_to_create):
                if "Offline" in entry_name:
                    measurement: C_CellCultureMeasurementsModel = sample.add(Child.create(C_CellCultureMeasurementsModel))
                    measurement.set_C_OtherSampleId_field(sample.get_OtherSampleId_field())
                    measurement.set_C_Technician_field(self.context.user.username)
                    measurement.set_C_SampleId_field(sample.get_SampleId_field())
                    measurement.set_C_PhaseStep_field(phase_step)
                elif "Online" in entry_name:
                    measurement: C_CellCultureOnLineMeasurementModel = sample.add(Child.create(C_CellCultureOnLineMeasurementModel))
                    measurement.set_C_SampleName_field(sample.get_OtherSampleId_field())
                    measurement.set_C_SampleID_field(sample.get_SampleId_field())
                    measurement.set_C_PhaseStep_field(phase_step)
                measurement.set_C_Timestamp_field(timestamp)
                new_measurements.append(measurement)
        return new_measurements

    def get_samples(self, measurements_entry: ExperimentEntry) -> List[SampleModel] | None:
        """
        Retrieves the list of samples based on the offline measurements table entry.

        :param measurements_entry: The ExperimentEntry to find the related samples for.
        :returns: A list of SampleModels from the related samples entry, or None if not found.
        """

        # We expect this entry to only be dependent on the samples entry.
        dependencies: list[int] = measurements_entry.dependency_set
        if not dependencies:
            return None

        # Get the sample table entry.
        sample_table_entry_id = dependencies.pop()
        sample_table_entry: ExperimentEntry = self.context.eln_manager.get_experiment_entry(
            self.context.eln_experiment.notebook_experiment_id, sample_table_entry_id)
        experiment_protocol = ElnExperimentProtocol(self.context.eln_experiment, self.context.user)
        samples_step = ElnEntryStep(experiment_protocol, sample_table_entry)

        # Get the samples.
        return self.experiment_handler.get_step_models(samples_step, SampleModel)

    def get_phase_step_from_entry(self, measurements_entry) -> str:

        eln_protocol = ElnExperimentProtocol(self.context.eln_experiment, self.context.user)
        measurements_entry = ElnEntryStep(eln_protocol, measurements_entry)

        options: dict[str, str] = measurements_entry.get_options()

        return options.get(ExperimentEntryTags.PHASE_STEP)
