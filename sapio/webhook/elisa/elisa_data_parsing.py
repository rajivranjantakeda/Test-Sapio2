import re
from statistics import stdev
from typing import List, Dict

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.datatype.attachment_util import AttachmentUtil
from sapiopycommons.eln.plate_designer import PlateDesignerEntry
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.Protocols import ElnEntryStep
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import WrappedType

from sapio.model.data_type_models import SampleModel, PlateDesignerWellElementModel, C_DilutedSampleModel, \
    C_ControlModel, ELNSampleDetailModel, AttachmentModel
from sapio.webhook.elisa.elisa_blocks import ElisaPlateBlock, ElisaDataBlock, ElisaSamplesBlockColumns
from sapio.webhook.elisa.elisa_entries import SampleData, SampleDataAverages


class ElisaParser:
    plate_block: ElisaPlateBlock
    data_blocks: Dict[str, ElisaDataBlock]

    def __init__(self):
        self.data_blocks = dict()

    def parse_elisa_file(self, elisa_file_path: str):
        """
        Constructs An ElisaPlateBlock and ElisaDataBlock objects based on the contents of the file.
        """
        # Get the elisa plate block section in between "Plate:" and "~End".
        # TODO: Determine if this is bad and if there should be a better regex to use.
        plate_block_pattern = re.compile(r"(Plate:.*?)~End", re.DOTALL)
        plate_block_match = plate_block_pattern.search(elisa_file_path)
        plate_block_str = plate_block_match.group(1)
        self.plate_block = ElisaPlateBlock(plate_block_str)

        # Get all the data block matches in the file, matching for "Group: " and "~End".
        data_block_pattern = re.compile(r"(Group:.*?)~End", re.DOTALL)
        data_block_matches = data_block_pattern.findall(elisa_file_path)
        for match in data_block_matches:
            data_block = ElisaDataBlock(match)
            self.data_blocks[data_block.group_name] = data_block


class ProcessElisaFile(CommonsWebhookHandler):
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Prompt the user for the ELISA file.
        file_info: (str, bytes) = CallbackUtil(context).request_file("ELISA Upload")
        file_name: str = file_info[0]
        file_bytes: bytes = file_info[1]

        # Store the file in the attachment entry (Raw Data File)
        # TODO: There is something very suspicious about this xls file at the moment, because it's actually just a
        #  TSV text file. It's so different that Sapio Office won't recognize it as an xls file. For now,
        #  we're going to change the extension to make sapio office happy.
        file_name = file_name.replace(".xls", ".tsv")
        attachment: AttachmentModel = AttachmentUtil.create_attachment(context, file_name, file_bytes, AttachmentModel)
        attachment.get_data_record().set_field_value(AttachmentModel.FILEPATH__FIELD_NAME.field_name, file_name)
        self.exp_handler.set_step_records("Raw Data File", [attachment])

        # Parse the file.
        elisa_parser = ElisaParser()
        elisa_parser.parse_elisa_file(file_bytes.decode("utf-16"))

        # Compile all file rows.
        all_rows: List[Dict[str, str]] = list()
        for block in elisa_parser.data_blocks.values():
            all_rows.extend(block.table_data)

        # Get the sources mapped by source position.
        plating_entry: ElnEntryStep = self.exp_handler.get_step("Plate Assignments")
        plate_designer: PlateDesignerEntry = PlateDesignerEntry(plating_entry, self.exp_handler)
        diluted_sample_sources: Dict[str, C_DilutedSampleModel] = self.get_sources_by_well_position(plate_designer, C_DilutedSampleModel)
        # control_sources: Dict[str, C_ControlModel] = self.get_sources_by_well_position(plate_designer, C_ControlModel)
        original_sample_sources: List[SampleModel] = self.exp_handler.get_step_models("Samples", SampleModel)

        # Update the sample data and sample data averages.
        sample_data: List[ELNSampleDetailModel] = self.update_sample_data(all_rows, diluted_sample_sources, original_sample_sources)
        self.update_sample_data_averages(sample_data, original_sample_sources)

        # All done
        self.rec_man.store_and_commit()
        return SapioWebhookResult(True, "Success!")

    def get_sources_by_well_position(self, plating_entry: PlateDesignerEntry, model_type: type[WrappedType]):
        # TODO: The current implementation of get sources relies on dependencies instead of grabbing sources based
        #  on the well elements. This is an alternate implementation. If the get_sources method changes, then this
        #  method should rely on that method from PlateDesignerEntry.
        # Grab the matching well elements.
        well_elements: List[PlateDesignerWellElementModel] = plating_entry.get_plate_designer_well_elements(PlateDesignerWellElementModel)
        well_elements_for_type = [element for element in well_elements if element.get_SourceDataTypeName_field() == model_type.get_wrapper_data_type_name()]
        # Query for the source records.
        source_ids: List[int] = [element.get_SourceRecordId_field() for element in well_elements_for_type]
        source_models: model_type = self.rec_handler.query_models_by_id(model_type, source_ids)
        source_models_by_id: Dict[int, model_type] = self.rec_handler.map_by_id(source_models)
        # Map the source models by well position.
        return_map = dict()
        for element in well_elements_for_type:
            source_id = element.get_SourceRecordId_field()
            source_model = source_models_by_id.get(source_id)
            return_map[element.get_RowPosition_field() + element.get_ColPosition_field()] = source_model
        return return_map

    def update_sample_data(self,
                           all_rows: List[Dict[str, str]],
                           diluted_sample_sources: Dict[str, C_DilutedSampleModel],
                           source_samples: List[SampleModel]) -> List[ELNSampleDetailModel]:

        # Delete existing step records.
        sample_data_step = self.exp_handler.get_step("Sample Data")
        existing_details: List[ELNSampleDetailModel] = self.exp_handler.get_step_models(sample_data_step, ELNSampleDetailModel)
        for detail in existing_details:
            detail.delete()

        # Prepare source samples for creating sample details
        source_samples_by_id = self.rec_handler.map_by_unique_field(source_samples, SampleModel.SAMPLEID__FIELD_NAME)

        # Create records for all of the sample data.
        new_sample_data: List[ELNSampleDetailModel] = list()
        for elisa_sample_row in all_rows:

            # Skip rows that don't have a CV value, as they are triplicates.
            cv = ElisaSamplesBlockColumns.CV.find(elisa_sample_row)
            if not cv:
                continue

            # Get the diluted sample
            well_position: str = ElisaSamplesBlockColumns.WELLS.find(elisa_sample_row)
            diluted_sample = diluted_sample_sources.get(well_position)
            if diluted_sample is None:
                continue

            source_sample: SampleModel = source_samples_by_id.get(diluted_sample.get_C_SampleId_field())
            if source_sample is None:
                continue

            # Create the sample data detail record.
            sample_data_detail = self.exp_handler.add_sample_details(sample_data_step, [source_sample], ELNSampleDetailModel).pop()

            # Set the sample id and sample name.
            sample_data_detail.set_SampleId_field(diluted_sample.get_C_SampleId_field())
            sample_data_detail.set_OtherSampleId_field(diluted_sample.get_C_OtherSampleId_field())

            # Set fields on the sample data details (I2S, Dilution #, Dilution Factor, and CV)
            # I2S is the mean result.
            i2s_str: str = ElisaSamplesBlockColumns.MEAN_RESULT.find(elisa_sample_row)
            if i2s_str:
                i2s = float(i2s_str)
                sample_data_detail.set_field_value(SampleData.I2S, i2s)
            # Dilution #
            sample_data_detail.set_field_value(SampleData.DILUTION, diluted_sample.get_C_DilutionNumber_field())
            # Dilution Factor.
            sample_data_detail.set_field_value(SampleData.DILUTION_FACTOR, diluted_sample.get_C_DilutionFactor_field())
            # CV%
            if cv:
                sample_data_detail.set_field_value(SampleData.CV, cv)

            new_sample_data.append(sample_data_detail)

        return new_sample_data

    def update_sample_data_averages(self, sample_data: List[ELNSampleDetailModel], source_samples: List[SampleModel]):
        # Group the sample data for sample id, so we can create averages per sample id.
        grouped_sample_data: Dict[str, List[ELNSampleDetailModel]] = self.rec_handler.map_by_field(sample_data, ELNSampleDetailModel.SAMPLEID__FIELD_NAME)

        # Delete the exisating averages.
        averages_step = self.exp_handler.get_step("Sample Data Averages")
        existing_averages: List[ELNSampleDetailModel] = self.exp_handler.get_step_models(averages_step, ELNSampleDetailModel)
        for average in existing_averages:
            average.delete()

        # Get the sample names mapped by sample id, so we can set sample name on the averages records.
        samples_by_sample_id = dict()
        for sample in source_samples:
            samples_by_sample_id[sample.get_SampleId_field()] = sample

        # Create the averages.
        for sample_id, sample_data_list in grouped_sample_data.items():
            # Find the sample.
            sample: SampleModel = samples_by_sample_id.get(sample_id)
            if sample is None:
                continue

            # Create the average record.
            average_record = self.exp_handler.add_sample_details(averages_step, [sample], ELNSampleDetailModel).pop()

            # Calculate average adjusted I2S value.
            adjusted_i2s_values = list()
            for sample_data in sample_data_list:
                # The adjusted i2s value is the i2s value multiplied by the dilution factor. On many rows, the
                # i2s value will be blank. In this case, we skip the row.
                i2s = sample_data.get_field_value(SampleData.I2S)
                if i2s is None:
                    continue
                dilution_factor = sample_data.get_field_value(SampleData.DILUTION_FACTOR)
                if dilution_factor is None:
                    continue
                adjusted_i2s_values.append(i2s * dilution_factor)

            # Calculate the average of the adjusted i2s values.
            average = None
            if len(adjusted_i2s_values) != 0:
                average = sum(adjusted_i2s_values) / len(adjusted_i2s_values)
                average_record.set_field_value(SampleDataAverages.AVG_I2S, average)

            # Calculate the InterDil CV% (100*standard_deviation/average) of adjusted i2s values.
            standard_deviation = None
            if len(adjusted_i2s_values) > 1:
                standard_deviation = stdev(adjusted_i2s_values)
            if standard_deviation is not None and average is not None and average != 0:
                cv = (100 * standard_deviation) / average
                average_record.set_field_value(SampleDataAverages.INTER_DIL_CV, cv)
