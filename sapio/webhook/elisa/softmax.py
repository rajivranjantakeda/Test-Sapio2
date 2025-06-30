from typing import List, Dict

from sapiopycommons.files.file_util import FileUtil
from sapiopycommons.files.file_writer import FileWriter
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext

from sapio.model.data_type_models import (PlateModel, PlateDesignerWellElementModel, C_DilutedSampleModel,
                                          C_DilutedControlModel)

WELL_LOCATION: str = "Well Location"
GROUP_NAME: str = "Group Name"
GROUP_TYPE: str = "Group Type"
SAMPLE_NAME: str = "Sample Name"
DESCRIPTOR1_NAME: str = "Descriptor1 Name"
DESCRIPTOR1_VALUE: str = "Descriptor1 Value"
DESCRIPTOR1_UNITS: str = "Descriptor1 Units"
DESCRIPTOR2_NAME: str = "Descriptor2 Name"
DESCRIPTOR2_VALUE: str = "Descriptor2 Value"
DESCRIPTOR2_UNITS: str = "Descriptor2 Units"


class SoftmaxGenerator:
    HEADERS = [
        WELL_LOCATION,
        GROUP_NAME,
        GROUP_TYPE,
        SAMPLE_NAME,
        DESCRIPTOR1_NAME,
        DESCRIPTOR1_VALUE,
        DESCRIPTOR1_UNITS,
        DESCRIPTOR2_NAME,
        DESCRIPTOR2_VALUE,
        DESCRIPTOR2_UNITS
    ]

    record_handler: RecordHandler

    def __init__(self, context: SapioWebhookContext):
        self.record_handler = RecordHandler(context.user)

    def generate_file(self, plate: PlateModel,
                      well_elements: List[PlateDesignerWellElementModel],
                      diluted_samples: List[C_DilutedSampleModel] = None,
                      diluted_controls: List[C_DilutedControlModel] = None) -> (str, bytes):
        """
        Generates the softmax output xls file for the given plate and well elements.
        """
        # Use a file writer to create the table file as a csv at first.
        writer: FileWriter = FileWriter(SoftmaxGenerator.HEADERS)

        # Sanitize inputs.
        if diluted_samples is None:
            diluted_samples = list()
        if diluted_controls is None:
            diluted_controls = list()

        # Prepare the source data to be accessible as we iterate.
        well_elements_by_position: Dict[str, PlateDesignerWellElementModel] = SoftmaxGenerator.__map_well_elements(well_elements)
        diluted_samples_by_id: Dict[int, C_DilutedSampleModel] = self.record_handler.map_by_id(diluted_samples)
        diluted_controls_by_id: Dict[int, C_DilutedControlModel] = self.record_handler.map_by_id(diluted_controls)

        # Iterate over the well elements and add them to the table.
        well_positions: List[str] = SoftmaxGenerator.__get_plate_well_positions(plate)
        for well_position in well_positions:
            # Get the current element
            well_element: PlateDesignerWellElementModel = well_elements_by_position.get(well_position)

            # Create the initial row data based on whether this is a control or dilution row.
            file_row: Dict[str, str] = dict()
            if well_element is not None:
                if well_element.get_IsControl_field():
                    file_row = self.__create_control_row(well_element)
                elif well_element.get_SourceDataTypeName_field() == C_DilutedSampleModel.DATA_TYPE_NAME:
                    diluted_sample: C_DilutedSampleModel = diluted_samples_by_id.get(well_element.get_SourceRecordId_field())
                    file_row = self.__create_sample_row(well_element, diluted_sample)
                elif well_element.get_SourceDataTypeName_field() == C_DilutedControlModel.DATA_TYPE_NAME:
                    diluted_control: C_DilutedControlModel = diluted_controls_by_id.get(well_element.get_SourceRecordId_field())
                    file_row = self.__create_diluted_control_row(well_element, diluted_control)

            # Populate the well position.
            file_row[WELL_LOCATION] = well_position
            writer.add_row_dict(file_row)

        # Build the file as a csv and convert it to an xls file.
        writer.delimiter = "\t"
        csv: str = writer.build_file()

        # xls_bytes = FileUtil.csv_to_xls(csv)
        return plate.get_PlateId_field() + "_Softmax.txt", bytearray(csv, "utf-8")


    @staticmethod
    def __get_plate_well_positions(plate: PlateModel) -> List[str]:
        """
        Iterate over the rows, and under each row iterate over the columns. Generate a well position string.
        The well position string is the row letter followed by the column number. The column number will always
        contain 2 digits (e.g. 01, 02, ..., 10, 11, 12).
        """
        num_rows: int = plate.get_PlateRows_field()
        num_cols: int = plate.get_PlateColumns_field()
        well_positions = list()
        for row_num in range(num_rows):
            row_letter = chr(65 + row_num)
            for col_num in range(num_cols):
                col_number = str(col_num + 1).zfill(2)
                well_position = row_letter + col_number
                well_positions.append(well_position)

        return well_positions

    @staticmethod
    def __map_well_elements(well_elements: List[PlateDesignerWellElementModel]) -> Dict[str, PlateDesignerWellElementModel]:
        """
        Maps the well elements by well position (row + column) where column will always have 2 digits.
        """
        well_elements_by_position = dict()
        for well_element in well_elements:
            row = well_element.get_RowPosition_field()
            col = well_element.get_ColPosition_field()
            well_position = row + col.zfill(2)
            well_elements_by_position[well_position] = well_element
        return well_elements_by_position

    @staticmethod
    def __create_control_row(well_element: PlateDesignerWellElementModel) -> Dict[str, str]:
        """
        Populates a dictionary with values based on a control well assignment.
        """

        # Default values.
        control_row = dict()
        control_row[GROUP_NAME] = "UNDEFINED"
        control_row[GROUP_TYPE] = "Custom"

        # Process different values when blank.
        is_blank = well_element.get_ControlType_field() == "Blank"
        if is_blank:
            control_row[GROUP_NAME] = "PBlank"
            control_row[GROUP_TYPE] = ""
        return control_row

    @staticmethod
    def __create_sample_row(well_element: PlateDesignerWellElementModel, diluted_sample: C_DilutedSampleModel) -> Dict[str, str]:
        """
        Populates a dictionary with values based on a diluted sample input and the well element record, following the
        format for dilution rows.
        """
        dilution_row = dict()
        dilution_row[GROUP_NAME] = "Sample"
        dilution_row[GROUP_TYPE] = "Custom"
        dilution_row[DESCRIPTOR1_NAME] = "Dilution Factor"
        if diluted_sample is not None:
            dilution_row[SAMPLE_NAME] = diluted_sample.get_C_OtherSampleId_field()
            dilution_row[DESCRIPTOR1_VALUE] = diluted_sample.get_C_DilutionFactor_field()
        return dilution_row

    @staticmethod
    def __create_diluted_control_row(well_element: PlateDesignerWellElementModel, diluted_control: C_DilutedControlModel) -> Dict[str, str]:
        """
        Populates a dictionary with values based on a diluted control input and the well element record, following the
        format for diluted control rows.
        """
        diluted_control_row = dict()
        # Constants.
        diluted_control_row[DESCRIPTOR1_NAME] = "Concentration"

        # Values dependent on diluted control.
        if diluted_control is not None:
            diluted_control_row[GROUP_NAME] = diluted_control.get_C_ConsumableClassification_field()
            diluted_control_row[GROUP_TYPE] = diluted_control.get_C_SoftmaxGroupType_field()
            diluted_control_row[SAMPLE_NAME] = diluted_control.get_C_DilutedControlName_field()
            diluted_control_row[DESCRIPTOR1_VALUE] = diluted_control.get_C_Concentration_field()
            diluted_control_row[DESCRIPTOR1_UNITS] = diluted_control.get_C_ConcentrationUnits_field()

        return diluted_control_row


