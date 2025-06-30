from typing import List, Dict

from sapiopycommons.files.file_util import FileUtil


class ElisaPlateBlock:
    """
    Represents the Plate block at the beginning of the elisa file.
    """
    value_by_well_position: Dict[str, float]

    def __init__(self, plate_block_str: str):
        """
        the plate block will contain all rows from ELISA file starting with "Plate:" and ending with "~End" (exclusive).
        The first line will be the plate line, and will be ignored.
        The second line will contain the column numbers.
        Each row after that will represent a row on the plate, which should be represented using an alphabetical letter.
        Each row will contain a series of values separated by tabs, which represent the values in each well.
        """
        self.value_by_well_position = dict()

        # Split the plate block into lines.
        plate_block_lines = plate_block_str.split("\r\n")

        # The first line is the plate line, which we can ignore.
        # The second line contains the column numbers.
        column_numbers = plate_block_lines[1].split("\t")
        # The rest of the lines contain the row data.
        row_data_lines = plate_block_lines[2:]
        for i in range(len(row_data_lines)):
            line = row_data_lines[i]
            row_letter = chr(65 + i) # Starting at A, and increasing.
            row_data = line.split("\t")
            for j in range(len(row_data)):
                column_number = column_numbers[j]
                if not row_data or not column_number:
                    continue
                well_position = str(row_letter) + column_number
                well_value = None
                file_value = row_data[j]
                if file_value:
                    well_value = float(file_value)
                self.value_by_well_position[well_position] = well_value

    def get_at(self, well_position: str):
        return self.value_by_well_position.get(well_position)


class ElisaDataBlock:
    """
    Represents all the blocks titled using the "Group:" tag in the elisa file.
    """
    group_name: str
    table_data: List[Dict[str, str]]
    column_definitions: List[Dict[str, str]]
    group_summaries = list[list[str]]

    def __init__(self, data_group_str: str):
        """
        The data group will be the contents of the file between "Group: " and "~End".

        The expected contents will follow the below format. Note that table-data, column-definitions, and
        group-summaries are all separated by two newline characters:
        <Group-Name>
        <table-data>

        <column-definitions>

        Group Summaries
        <Group-Summary-Data>
        """

        # Separate the first line from the rest of the file. This is the line containing the group name.
        first_split = data_group_str.split("\r\n", 1)
        self.group_name = first_split[0].removeprefix("Group: ").strip()
        data_group_body: str = first_split[1]

        # Now split this body into the table data, column definitions, and group summaries by two newlines.
        body_split = data_group_body.split("\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\r\n")
        table_data_str = body_split[0]
        column_definitions_str = None
        if len(body_split) > 1:
            column_definitions_str = body_split[1]
        group_summaries_str = None
        if len(body_split) > 2:
            group_summaries_str = body_split[2]

        # Now parse out each of those sections.
        self.table_data = self.parse_table_data(table_data_str)
        if column_definitions_str:
            self.column_definitions = self.parse_column_definitions(column_definitions_str)
        if group_summaries_str:
            self.group_summaries = self.parse_group_summaries(group_summaries_str)

    def parse_table_data(self, table_data_str: str):
        # TODO: Should the headers be required here? They vary based on the group, so that may need to be a parameter.
        tokenized_table: tuple[list[dict[str, str]], list[list[str]]] = FileUtil.tokenize_csv(table_data_str.encode(), seperator="\t")
        table_rows = tokenized_table[0]
        return table_rows

    def parse_column_definitions(self, column_definitions_str: str):
        # TODO: Should there be required headers for column definitions, or more advanced parsing for column defs?
        tokenized_table = FileUtil.tokenize_csv(column_definitions_str.encode(), seperator="\t")
        column_definitions = tokenized_table[0]
        return column_definitions

    def parse_group_summaries(self, group_summaries_str: str):
        # Remove the section title, and then break down the group summaries into rows.
        group_summaries_body: str = group_summaries_str.removeprefix("Group Summaries\r\n")
        rows: List[str] = group_summaries_body.split("\r\n")
        result_rows: List[List[str]] = list()
        for row in rows:
            result_rows.append(row.split("\t"))
        return result_rows


class ColumnKeys:
    """ Represents all valid column values representing this value. """
    valid_keys: List[str]

    def __init__(self, *args):
        for key in args:
            if not isinstance(key, str):
                raise ValueError("ColumnKeys can only be initialized with strings.")
        self.valid_keys = list(args)

    def find(self, row_map: Dict[str, str]) -> str | None:
        for key in self.valid_keys:
            if key in row_map:
                return row_map[key]
        return None


class ElisaSamplesBlockColumns:
    SAMPLE = ColumnKeys("Sample")
    WELLS = ColumnKeys("Wells", "Well")
    DILUTION_FACTOR = ColumnKeys("DilutionFactor", "Dilution Factor")
    VALUES = ColumnKeys("Values")
    RESULT = ColumnKeys("Result")
    MEAN_RESULT = ColumnKeys("MeanResult", "Mean Result")
    ADJ_RESULT = ColumnKeys("Adj.Result")
    MEAN_ADJ_RESULT = ColumnKeys("Mean Adj.Result")
    STD_DEV = ColumnKeys("StdDev", "Std.Dev.")
    CV = ColumnKeys("CV", "CV%", "CV% Result")

    @classmethod
    def get_all_columns(cls):
        return [
            cls.SAMPLE, cls.WELLS, cls.DILUTION_FACTOR,
            cls.VALUES, cls.RESULT, cls.MEAN_RESULT,
            cls.ADJ_RESULT, cls.MEAN_ADJ_RESULT,
            cls.STD_DEV, cls.CV
        ]
