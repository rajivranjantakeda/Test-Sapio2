import statistics
from typing import List, Dict

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.datatype.attachment_util import AttachmentUtil
from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.files.file_util import FileUtil
from sapiopycommons.general.exceptions import SapioCriticalErrorException
from sapiopycommons.general.time_util import TimeUtil
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep
from sapiopylib.rest.utils.recordmodel.PyRecordModel import PyRecordModel
from sapiopylib.rest.utils.recordmodel.RecordModelManager import RecordModelManager, RecordModelInstanceManager
from sapiopylib.rest.utils.recordmodel.RecordModelUtil import RecordModelUtil
from scipy.stats import linregress

from sapio.model.data_type_models import ELNSampleDetailModel, AttachmentModel, ELNExperimentDetailModel, C_DilutedSampleModel, SampleModel
from sapio.model.eln_classes import ELNExperimentDetail, ELNSampleDetail
from sapio.webhook.hplc.entries import HPLCRawDataFields, SlopeInterceptFields, ReferenceStandardDataFields, \
    AssayControlDataFields, SampleDataFields, SampleDilutionFields
from sapio.webhook.hplc.stats import LinRegressData

from sapio.manager.manager_retrievals import Manager

RETENTION_TIME = "Retention Time"
USP_TAILING = "USP Tailing"
USP_PLATE_COUNT = "USP Plate Count"
AREA = "Area"
DATE_ACQUIRED = "Date Acquired"
NAME = "Name"
SAMPLE_NAME = "SampleName"

class EmpowerEntryInitialization(CommonsWebhookHandler):

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Get the File from the attachment entry.
        attachments: List[AttachmentModel] = self.exp_handler.get_step_models("Raw Data File Upload", AttachmentModel)
        if len(attachments) < 1:
            return SapioWebhookResult(False, "No file attached.")
        attachment_record = attachments.pop()

        return EmpowerParser(context).parse(attachment_record)

class EmpowerReUploadFile(CommonsWebhookHandler):

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        raw_file_entry_name: str = context.experiment_entry.entry_name

        # Get the File from the attachment entry and delete it so it can be replaced
        attachments: List[AttachmentModel] = self.exp_handler.get_step_models(raw_file_entry_name, AttachmentModel)

        if len(attachments) > 0:
            for attachment in attachments:
                attachment.delete()

        # Prompt the user for the ELISA file.
        file_info: (str, bytes) = CallbackUtil(context).request_file("HPLC Upload")
        file_name: str = file_info[0]
        file_bytes: bytes = file_info[1]

        attachment_record: AttachmentModel = AttachmentUtil.create_attachment(context, file_name, file_bytes, AttachmentModel)
        attachment_record.get_data_record().set_field_value(AttachmentModel.FILEPATH__FIELD_NAME.field_name, file_name)
        self.exp_handler.set_step_records(raw_file_entry_name, [attachment_record])

        return EmpowerParser(context).parse(attachment_record)


class EmpowerParser:
    """
    This webhook is to be invoked one time inside the HPLC experiment. It is intended to be invoked on initialization
    of the raw data file attachment entry after the attachment has been uploaded. The Parser reads through the rows
    in the file and populates several experiment entries based on that.
    """
    HEADERS = [
        SAMPLE_NAME,
        NAME,
        DATE_ACQUIRED,
        AREA,
        USP_PLATE_COUNT,
        USP_TAILING,
        RETENTION_TIME]
    """ These are the required headers expected to be found in the raw data file. """

    context: SapioWebhookContext | None
    exp_handler: ExperimentHandler | None
    rec_man: RecordModelManager | None
    inst_man: RecordModelInstanceManager | None
    rec_handler: RecordHandler | None

    def __init__(self, context: SapioWebhookContext):
        self.context = context
        self.exp_handler = Manager.experiment_handler(context)
        self.rec_man = Manager.record_model_manager(context)
        self.inst_man = Manager.record_model_instance_manager(context)
        self.rec_handler = Manager.record_handler(context)

    def parse(self, attachment_record: AttachmentModel) -> SapioWebhookResult:

        # Remove all the quotes to simplify tokenization and parsing.
        file_bytes: bytes = AttachmentUtil.get_attachment_bytes(self.context, attachment_record)
        file_str = file_bytes.decode().replace("\"", "")
        file_bytes = file_str.encode()

        # Tokenize the file, and get the maps.
        tokenized_file = FileUtil.tokenize_csv(file_bytes, self.HEADERS, seperator='\t')
        row_maps: List[Dict[str, str]] = tokenized_file[0]

        # Sort the data into groups based on the contents of sample name.
        assay_control_data: List[Dict[str, str]] = list()
        reference_standards_data: List[Dict[str, str]] = list()
        raw_standard_curve_data: List[Dict[str, str]] = list()
        raw_sample_data: List[Dict[str, str]] = list()
        for row_map in row_maps:
            sample_name = row_map.get(SAMPLE_NAME)
            if "Assay Control" in sample_name:
                assay_control_data.append(row_map)
            elif "mg/mL RS" in sample_name:
                reference_standards_data.append(row_map)
            elif "ug RS" in sample_name:
                raw_standard_curve_data.append(row_map)
            else:
                raw_sample_data.append(row_map)

        # Get all the relevant data entries.
        reference_standards_entry: ElnEntryStep =  self.exp_handler.get_step("1mg/mL Reference Standard Conditioning")
        raw_standards_entry: ElnEntryStep = self.exp_handler.get_step("Raw Standard Curve Data")
        assay_controls_entry: ElnEntryStep = self.exp_handler.get_step("Raw Assay Control Data")
        raw_sample_data_entry: ElnEntryStep = self.exp_handler.get_step("Raw Sample Data")

        # Clear out and re-populate ELN Raw data entries for standards and controls.
        self.mark_records_for_deletion(reference_standards_entry)
        self.mark_records_for_deletion(raw_standards_entry)
        self.mark_records_for_deletion(assay_controls_entry)
        reference_standards_data_models = self.populate_eln_raw_data_entry(reference_standards_data, reference_standards_entry.eln_entry.data_type_name)
        standard_curve_data_models = self.populate_eln_raw_data_entry(raw_standard_curve_data, raw_standards_entry.eln_entry.data_type_name)
        assay_control_data_models = self.populate_eln_raw_data_entry(assay_control_data, assay_controls_entry.eln_entry.data_type_name)

        # Populate the raw sample data entry.
        raw_data_detail_models: List[ELNSampleDetailModel] = self.populate_sample_raw_data_entry(raw_sample_data, raw_sample_data_entry)

        # Populate the System sustainability tab.
        linear_regression_data: LinRegressData = self.populate_slope_intercept_entry(standard_curve_data_models)
        self.populate_reference_standard_data_entry(standard_curve_data_models, linear_regression_data)
        self.populate_assay_control_data_entry(assay_control_data_models, linear_regression_data)

        # Populate the results tab.
        self.populate_sample_data_entry(raw_data_detail_models, linear_regression_data)

        # All done.
        self.rec_man.store_and_commit()
        return SapioWebhookResult(True)

    def populate_eln_raw_data_entry(self, raw_data: List[Dict[str, str]], data_type_name: str):
        """
        Instantiates record models with a data type of 'data_type_name' for each dictionary in 'raw_data'.
        The data type must be an ELNExperimentDetail entry with data field names matching the ones specified in the
        HPLCRawDataFields class. Because the entry is an ELNExperimentDetail entry, there is no need to add the
        subsequently created records to the entry directly.

        :param raw_data: The list of dictionaries representing the file rows to process and convert into data records.
        :param data_type_name: The data type name of the ELNExperimentDetail entry to create records for.
        """
        raw_data_models: List[PyRecordModel] = list()
        for file_row in raw_data:

            # Create the experiment detail record, and set the HPLC fields.
            experiment_detail: PyRecordModel = self.inst_man.add_new_record(data_type_name)

            # Get the sample's sample name, which is already a str.
            sample_name = file_row.get(SAMPLE_NAME)
            experiment_detail.set_field_value(HPLCRawDataFields.SAMPLE_NAME, sample_name)

            # Get the name value, which is already a str.
            name: str = file_row.get(NAME)
            experiment_detail.set_field_value(HPLCRawDataFields.NAME, name)

            # Parse date acquired, including the timezone.
            # The time zone will be separated by a space at the end of the field. The time zone will be in pythons
            # standard way of formatting time zones as str values.
            # The date will be formatted as "%A, %B %d, %Y %I:%M:%S %p
            date_acquired: str = file_row.get(DATE_ACQUIRED)
            if date_acquired:
                last_space_index = date_acquired.rfind(" ")
                timezone_start = last_space_index + 1
                time_zone_str = date_acquired[timezone_start:]
                timestamp: str = date_acquired[0:last_space_index]

                if timestamp and time_zone_str:
                    date_acquired_milis: int = TimeUtil.format_to_millis(timestamp, "%A, %B %d, %Y %I:%M:%S %p", time_zone_str)
                    experiment_detail.set_field_value(HPLCRawDataFields.DATE_ACQUIRED, date_acquired_milis)

            # Get the area value, which needs to be an int.
            area_str: str = file_row.get(AREA)
            if area_str:
                area: int = int(area_str)
                experiment_detail.set_field_value(HPLCRawDataFields.AREA, area)

            # Get the USP Plate Count value, as a float.
            usp_plate_count_str: str = file_row.get(USP_PLATE_COUNT)
            if usp_plate_count_str:
                usp_plate_count: float = float(usp_plate_count_str)
                experiment_detail.set_field_value(HPLCRawDataFields.USP_PLATE_COUNT, usp_plate_count)

            # Get the USP Trailing value as a float.
            usp_trailing_str: str = file_row.get(USP_TAILING)
            if usp_trailing_str:
                usp_trailing: float = float(usp_trailing_str)
                experiment_detail.set_field_value(HPLCRawDataFields.USP_TAILING, usp_trailing)

            # Get the Retention Time, as a float.
            retention_time_str: str = file_row.get(RETENTION_TIME)
            if retention_time_str:
                retention_time: float = float(retention_time_str)
                experiment_detail.set_field_value(HPLCRawDataFields.RETENTION_TIME, retention_time)

            raw_data_models.append(experiment_detail)

        return raw_data_models

    def populate_sample_raw_data_entry(self, raw_sample_data: List[Dict[str, str]], raw_sample_data_entry: ElnEntryStep) -> List[ELNSampleDetailModel]:
        """
        Maps the raw data from the file to the existing sample detail records in the entry. Rows from the file are
        matched to existing sample detail records by sample name. If no sample match is found, results are ignored.

        :param raw_sample_data: The list of dictionaries representing rows from the file.
        :param raw_sample_data_entry: The entry for setting raw sample data values onto.
        """
        # Get the existing sample details record models.
        existing_details: List[ELNSampleDetailModel] = self.exp_handler.get_step_models(
            raw_sample_data_entry, ELNSampleDetailModel)

        # Blank out existing values for the fields we are going to populate.
        for existing_detail in existing_details:
            existing_detail.set_field_value(HPLCRawDataFields.NAME, None)
            existing_detail.set_field_value(HPLCRawDataFields.DATE_ACQUIRED, None)
            existing_detail.set_field_value(HPLCRawDataFields.AREA, None)
            existing_detail.set_field_value(HPLCRawDataFields.USP_PLATE_COUNT, None)
            existing_detail.set_field_value(HPLCRawDataFields.USP_TAILING, None)
            existing_detail.set_field_value(HPLCRawDataFields.RETENTION_TIME, None)

        # Map them by Sample Name, to match against the file rows.
        existing_details_by_id: Dict[str, ELNSampleDetailModel] = self.rec_handler.map_by_unique_field(
            existing_details, ELNSampleDetailModel.SAMPLEID__FIELD_NAME)

        for file_row in raw_sample_data:
            # Get the existing sample detail for this row.
            sample_name: str = file_row.get(SAMPLE_NAME)
            existing_sample_detail: ELNSampleDetailModel = existing_details_by_id.get(sample_name)
            if existing_sample_detail is None:
                continue

            # Get the name value, which is already a str.
            name: str = file_row.get(NAME)

            # Parse date acquired, including the timezone.
            # The time zone will be separated by a space at the end of the field. The time zone will be in pythons
            # standard way of formatting time zones as str values.
            # The date will be formatted as "%A, %B %d, %Y %I:%M:%S %p
            date_acquired: str = file_row.get(DATE_ACQUIRED)
            last_space_index = date_acquired.rfind(" ")
            timezone_start = last_space_index + 1
            time_zone_str = date_acquired[timezone_start:]
            timestamp: str = date_acquired[0:last_space_index]
            date_acquired_milis: int = TimeUtil.format_to_millis(timestamp, "%A, %B %d, %Y %I:%M:%S %p", time_zone_str)

            # Get the area value, which needs to be an int.
            area_str: str = file_row.get(AREA)
            area: int = int(area_str)

            # Get the USP Plate Count value, as a float.
            usp_plate_count_str: str = file_row.get(USP_PLATE_COUNT)
            usp_plate_count: float = float(usp_plate_count_str)

            # Get the USP Trailing value as a float.
            usp_trailing_str: str = file_row.get(USP_TAILING)
            usp_trailing: float = float(usp_trailing_str)

            # Get the Retention Time, as a float.
            retention_time_str: str = file_row.get(RETENTION_TIME)
            retention_time: float = float(retention_time_str)

            # Set the data onto the sample detail model.
            existing_sample_detail.set_field_value(HPLCRawDataFields.NAME, name)
            existing_sample_detail.set_field_value(HPLCRawDataFields.DATE_ACQUIRED, date_acquired_milis)
            existing_sample_detail.set_field_value(HPLCRawDataFields.AREA, area)
            existing_sample_detail.set_field_value(HPLCRawDataFields.USP_PLATE_COUNT, usp_plate_count)
            existing_sample_detail.set_field_value(HPLCRawDataFields.USP_TAILING, usp_trailing)
            existing_sample_detail.set_field_value(HPLCRawDataFields.RETENTION_TIME, retention_time)

        return existing_details

    def populate_slope_intercept_entry(self, data: List[PyRecordModel]) -> LinRegressData:
        """
        Given a set of Raw Data record models, runs a linear regression analysis on the Concentration and Area values.
        This method is specifically adapted to pull the concentration from the sample name off of the Standard Curve
        Raw Data experiment details. The Concentration values from these samples names are used as the x values, and
        the Area values will be used as the y values.

        :param data: The record models that will be used to compute the linear regression and generate the values for
            the slope / intercept entry.
        :returns: A LinRegressData object that has easier references to the linear regression data needed.
        """

        # Grab the existing record for the entry.
        intercept_details = self.exp_handler.get_step_models("Slope / Intercept", ELNExperimentDetailModel)
        if len(intercept_details) != 1:
            raise SapioCriticalErrorException("The 'Slope / Intercept' entry does not have a record to populate. "
                                              + "Please contact a system administrator.")
        intercept_detail = intercept_details.pop()

        # Compile the areas and concentration values.
        areas = RecordModelUtil.get_value_list(data, HPLCRawDataFields.AREA)
        concentrations = list()
        for record in data:
            sample_name = record.get_field_value(HPLCRawDataFields.SAMPLE_NAME)
            concentration_text = sample_name.removesuffix("ug RS")
            # TODO the values in the file are ints, but I used float for safety. Should I?
            conc_value: float = float(concentration_text)
            concentrations.append(conc_value)

        # Calculate the linear regression details, and set the values on this record.
        result = LinRegressData(linregress(concentrations, areas))
        intercept_detail.set_field_value(SlopeInterceptFields.SLOPE, result.get_slope())
        intercept_detail.set_field_value(SlopeInterceptFields.INTERCEPT, result.get_intercept())
        intercept_detail.set_field_value(SlopeInterceptFields.R2, result.get_r_squared())
        intercept_detail.set_field_value(SlopeInterceptFields.SPEC, "≥0.99")
        return result


    def populate_reference_standard_data_entry(self, raw_data_models: List[PyRecordModel], regression_data: LinRegressData):
        """
        Given the raw data experiment detail models, and a LinRegressionData object, populates the entry containing
        Reference Standard Data. Removes any existing records.

        :param raw_data_models: The raw data reference standard experiment detail, as PyRecordModels.
        :param regression_data: A LineRegressData generated from the standard curve data.
        """
        reference_standards_data_step = self.exp_handler.get_step("Reference Standard Data")
        self.mark_records_for_deletion(reference_standards_data_step)

        # Iterate over the reference standard data, and populate the table.
        for record in raw_data_models:
            # New record.
            reference_standard_data_row = self.inst_man.add_new_record(reference_standards_data_step.eln_entry.data_type_name)

            # Set Sample Name
            sample_name: str = record.get_field_value(HPLCRawDataFields.SAMPLE_NAME)
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.SAMPLE_NAME, sample_name)

            # Retention Time
            retention_time: float = record.get_field_value(HPLCRawDataFields.RETENTION_TIME)
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.MAIN_PEAK_RETENTION_TIME, retention_time)

            # Area
            area: int = record.get_field_value(HPLCRawDataFields.AREA)
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.MAIN_PEAK_AREA, area)

            # y - b
            y_minus_b: None | float = None
            if area is not None and regression_data.get_intercept() is not None:
                y_minus_b = area - regression_data.get_intercept()
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.Y_MINUS_B, y_minus_b)

            # m
            slope = regression_data.get_slope()
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.M, slope)

            # Concentration
            concentration = None
            if y_minus_b is not None and slope is not None and slope != 0:
                concentration = y_minus_b / slope
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.CONCENTRATION, concentration)

            # % Recovery
            original_conc = float(sample_name.removesuffix("ug RS"))
            percent_recovery = None
            if original_conc is not None and original_conc != 0:
                percent_recovery = (concentration / original_conc) * 100
            reference_standard_data_row.set_field_value(ReferenceStandardDataFields.PERCENT_RECOVERY, percent_recovery)

    def populate_assay_control_data_entry(self, raw_data_models: List[PyRecordModel], linear_regression_data: LinRegressData):
        """
        Populates the Assay Control Data entry.

        :param raw_data_models: The PyRecordModels storing raw data for assay controls.
        :param linear_regression_data: The LineRegressData created form the standard curve data.
        """
        assay_control_data_step = self.exp_handler.get_step("Assay Control Data")
        self.mark_records_for_deletion(assay_control_data_step)

        # Calculate Average Area.
        areas = RecordModelUtil.get_value_list(raw_data_models, HPLCRawDataFields.AREA)
        average_area = statistics.mean(areas)

        # Iterate over the assay control data, and populate the table.
        new_data: List[PyRecordModel] = list()
        for record in raw_data_models:
            # New record.
            assay_control_data_row: PyRecordModel = self.inst_man.add_new_record(assay_control_data_step.eln_entry.data_type_name)

            # Set Sample Name
            sample_name = record.get_field_value(HPLCRawDataFields.SAMPLE_NAME)
            assay_control_data_row.set_field_value(AssayControlDataFields.SAMPLE_NAME, sample_name)

            # Area
            area = record.get_field_value(HPLCRawDataFields.AREA)
            assay_control_data_row.set_field_value(AssayControlDataFields.AREA, area)

            # Average Peak Area
            assay_control_data_row.set_field_value(AssayControlDataFields.AVERAGE_PEAK_AREA, average_area)

            # USP Plate Count
            usp_plate_count = record.get_field_value(HPLCRawDataFields.USP_PLATE_COUNT)
            assay_control_data_row.set_field_value(AssayControlDataFields.USP_PLATE_COUNT, usp_plate_count)

            # USP Tailing
            usp_tailing = record.get_field_value(HPLCRawDataFields.USP_TAILING)
            assay_control_data_row.set_field_value(AssayControlDataFields.USP_TAILING, usp_tailing)

            # Retention Time
            retention_time = record.get_field_value(HPLCRawDataFields.RETENTION_TIME)
            assay_control_data_row.set_field_value(AssayControlDataFields.RETENTION_TIME, retention_time)

            # Injection volume (?)
            injection_volume = 10
            assay_control_data_row.set_field_value(AssayControlDataFields.INJECTION_VOLUME, injection_volume)

            # Concentration
            intercept = linear_regression_data.get_intercept()
            slope = linear_regression_data.get_slope()
            concentration: float | None = None
            if slope != 0 and injection_volume != 0:
                concentration = abs((area - intercept) / slope) / injection_volume
                assay_control_data_row.set_field_value(AssayControlDataFields.CONCENTRATION, concentration)

            # Percent Difference
            if concentration is not None:
                percent_difference = abs(concentration-0.5) / 0.5
                assay_control_data_row.set_field_value(AssayControlDataFields.DIFFERENCE, percent_difference)

            # Spec values
            assay_control_data_row.set_field_value(AssayControlDataFields.USP_PLATE_COUNT_SPEC, "≥ 5000")
            assay_control_data_row.set_field_value(AssayControlDataFields.USP_TAILING_SPEC, "0.70-1.50")
            assay_control_data_row.set_field_value(AssayControlDataFields.RETENTION_TIME_SPEC, "1.5 - 2.5")
            assay_control_data_row.set_field_value(AssayControlDataFields.CONCENTRATION_SPEC, "0.465 - 0.535")
            assay_control_data_row.set_field_value(AssayControlDataFields.DIFFERENCE_SPEC, "≤ 7%")

            # Add to our list.
            new_data.append(assay_control_data_row)

        # Calculate the average concentration, so long as all of the concentration values exist.
        concentration_values = RecordModelUtil.get_value_list(new_data, AssayControlDataFields.CONCENTRATION)
        if None in concentration_values:
            return
        average_concentration = statistics.mean(concentration_values)
        for record in new_data:
            record.set_field_value(AssayControlDataFields.AVERAGE_CONCENTRATION, average_concentration)

    def populate_sample_data_entry(self, raw_data_models: List[ELNSampleDetailModel], linear_regression: LinRegressData):
        """
        Populate the "Sample Data" entry data using the raw sample data models and the linear regression of the assay
        control data.

        :param raw_data_models: The sample detail models for the raw data of the samples.
        :param linear_regression: The linear regression done on the standard curve data.
        """

        # Get the dilution details prepared for the result calculations.
        dilution_details: list[C_DilutedSampleModel] = self.exp_handler.get_step_models("Diluted Samples", C_DilutedSampleModel)
        dilution_details_by_id: Dict[str, C_DilutedSampleModel] = self.rec_handler.map_by_unique_field(
            dilution_details, C_DilutedSampleModel.C_SAMPLEID__FIELD_NAME.field_name)

        self.rec_man.relationship_manager.load_parents_of_type(
            wrapped_records=dilution_details,
            parent_wrapper_type=SampleModel)

        # Get the result detail models that we will need to populate.
        result_detail_models = self.exp_handler.get_step_models("Sample Data", ELNSampleDetailModel)
        result_details_by_id: Dict[str, ELNSampleDetailModel] = self.rec_handler.map_by_unique_field(
            result_detail_models, ELNSampleDetail.SAMPLE_ID)

        # Before setting values, ensure that we remove any old values from the result details.
        for result_detail in result_detail_models:
            result_detail.set_field_value(SampleDataFields.PEAK_AREA, None)
            result_detail.set_field_value(SampleDataFields.INTERCEPT, None)
            result_detail.set_field_value(SampleDataFields.SLOPE, None)
            result_detail.set_field_value(SampleDataFields.DILUTION_FACTOR, None)
            result_detail.set_field_value(SampleDataFields.INJECTION_VOLUME, None)
            result_detail.set_field_value(SampleDataFields.ESTIMATED_CONCENTRATIONS, None)

        # Iterate over the raw data, and populate the result data.
        for raw_data_model in raw_data_models:
            # Match on result model by sample id. Skip samples that don't have any raw data.
            sample_id: str = raw_data_model.get_field_value(ELNExperimentDetail.SAMPLE_ID)
            result_model: ELNSampleDetailModel = result_details_by_id.get(sample_id)
            if result_model is None:
                continue

            # Match on dilution details by sample id.
            dilution_model: C_DilutedSampleModel = dilution_details_by_id.get(sample_id)

            # Peak Area
            area = raw_data_model.get_field_value(HPLCRawDataFields.AREA)
            result_model.set_field_value(SampleDataFields.PEAK_AREA, area)

            # Intercept
            intercept = linear_regression.get_intercept()
            result_model.set_field_value(SampleDataFields.INTERCEPT, intercept)

            # Slope
            result_model.set_field_value(SampleDataFields.SLOPE, linear_regression.get_slope())

            # Don't populate the fields dependent on dilution details if dilution details aren't found.
            if dilution_model is None:
                continue

            # Dilution Factor
            dilution_factor = dilution_model.get_C_DilutionFactor_field()
            result_model.set_field_value(SampleDataFields.DILUTION_FACTOR, dilution_factor)

            # Injection Volume
            injection_volume = dilution_model.get_C_InjectionVolume_field()
            result_model.set_field_value(SampleDataFields.INJECTION_VOLUME, injection_volume)

            # Estimated Concentration
            estimated_concentration = self.get_estimated_concentration_from_diluted_sample(dilution_model)

            if estimated_concentration:
                result_model.set_field_value(SampleDataFields.ESTIMATED_CONCENTRATIONS, estimated_concentration)

    def mark_records_for_deletion(self, experiment_detail_entry: ElnEntryStep):
        """
        Makes 1 webservice call to retrieve the records for the entry. Iterates over the records, and marks the record
        model for deletion.
        """
        details = self.exp_handler.get_step_models(experiment_detail_entry, ELNExperimentDetailModel)
        for eln_detail in details:
            eln_detail.delete()

    def get_estimated_concentration_from_diluted_sample(self, dilution_model: C_DilutedSampleModel):

        for sample in dilution_model.get_parents_of_type(parent_type=SampleModel):
            return sample.get_Concentration_field()

        return None
