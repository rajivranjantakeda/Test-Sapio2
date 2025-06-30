import re
from io import BytesIO
from typing import List, Dict, Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, StyleSheet1, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, PageTemplate, frames, FrameBreak, paragraph
from sapiopycommons.general.aliases import UserIdentifier, AliasUtil
from sapiopycommons.general.exceptions import SapioUserErrorException, SapioUserCancelledException
from sapiopycommons.general.time_util import TimeUtil
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopylib.rest.ClientCallbackService import ClientCallback
from sapiopylib.rest.User import SapioUser
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition, FieldType, \
    VeloxIntegerFieldDefinition
from sapiopylib.rest.pojo.webhook.ClientCallbackRequest import FormEntryDialogRequest
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.utils.DataTypeCacheManager import DataTypeCacheManager
from sapiopylib.rest.utils.FormBuilder import FormBuilder
from sapiopylib.rest.utils.recordmodel.PyRecordModel import PyRecordModel
from sapiopylib.rest.utils.recordmodel.RecordModelManager import RecordModelRelationshipManager
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import WrappedRecordModel, RecordModelWrapperUtil
from sapiopylib.rest.utils.recordmodel.ancestry import RecordModelAncestorManager

from sapio.manager.manager_retrievals import Manager
from sapio.model.data_type_models import C_TakedaLabelDefinitionModel


class LabelMacroManager:
    """
    A class for replacing macros within the structured definition of a label.
    """
    root_regex = r"\[(\w+)\]"  # Regex for root record macros.
    context: SapioWebhookContext  # Context as needed.
    type_cache: DataTypeCacheManager  # Type cache for checking field types on data types.

    def __init__(self, context: SapioWebhookContext):
        self.context = context
        TimeUtil.set_default_timezone("est")  # TODO: determine proper time zone.
        self.type_cache = DataTypeCacheManager(context.user)

    def format_value(self, record: PyRecordModel, field: str) -> str:
        """
        Formats the field value from the given record for the given field.

        Makes a webservice request if the data type has not already had it's fields loaded.

        :param record: The record to get the value from.
        :param field: The dataFieldName to get the value for and to format.
        :return: The formatted str value. If the value is None or if the field def does not exist, an empty string is
            returned.
        """
        # Get the current value from the record. Return blank if empty.
        value = record.get_field_value(field)
        if value is None or value == "":
            return ""

        # Get the field definition from the records data type. return blank if not found.
        field_defs: Dict[str, AbstractVeloxFieldDefinition] = self.type_cache.get_fields_for_type(record.data_type_name)
        field_def = field_defs.get(field)
        if field_def is None:
            return ""

        # Format the field based on the definition.
        match field_def.data_field_type:
            case FieldType.DATE:
                # TODO: convert java format from date def to python format?
                return TimeUtil.millis_to_format(value, "%d-%m-%Y")
            case _:
                return str(value)

    def compute_root_record_replacements(self, label_text: str, root_record: PyRecordModel) -> Dict[str, list[str]]:
        """
        Compile the collection of values matching to the root record macros in the structured label definition text.

        :param label_text: The structured text to search for macros and compile values based on.
        :param root_record: The record to use for compiling macro values.
        :returns: A dictionary where the keys are the macro to replace, and the value is the
        """
        macros = dict()
        for match in re.findall(LabelMacroManager.root_regex, label_text):
            field_str = match
            field_value = self.format_value(root_record, field_str)
            field_macro = "[" + field_str + "]"
            macros.setdefault(field_macro, list()).append(field_value)
        return macros

    def compute_related_record_replacements(self, label_text: str, record_list) -> Dict[str, list[str]]:
        """
        Compile the collection of values matching to the related record macros in the structured label definition text.

        :param label_text: The structured text to search for macros and compile values based on.
        :param record_list: The list of records to iterate over when compiling values for the macros.
        :returns: A dictionary where the keys are the macro to replace, and the values are all of the valid values for
            that macro.
        """
        macros = dict()
        for record in record_list:
            data_type: str = record.data_type_name
            related_record_macro = r"\[{0}\.(\w+)\]".format(data_type)
            # Replace non-root regex first.
            for match in re.findall(related_record_macro, label_text):
                field_str = match
                field_value = self.format_value(record, field_str)
                field_macro = "[" + data_type + "." + field_str + "]"
                macros.setdefault(field_macro, list()).append(field_value)
        return macros

    def load_related_records(self, records: List[WrappedRecordModel], label_definition: str):
        """
        Finds all related record macros  in the label definition and loads the ancestors based on the data types within
        those macros. Executes 'n' webservice calls where 'n' is the number of distinct ancestor data types within the
        label definition.

        :param records: A list of wrapped record models that will have ancestors loaded based on the macros within the
            label definition.
        :param label_definition: The str value of the structured label definition to scan for related record macros.
        """
        ancestor_manager = Manager.record_model_ancestor_manager(self.context)
        related_record_types: list[str] = self.get_related_record_types(label_definition)
        for data_type in related_record_types:
            ancestor_manager.load_ancestors_of_type(RecordModelWrapperUtil.unwrap_list(records), data_type)
        return

    def get_related_records(self, root_record: PyRecordModel, label_definition: str) -> (
            List)[PyRecordModel]:
        """
        Returns the related records for the root record based on the label definitions related record macros.

        :param root_record: The root record to get the related records from.
        :param label_definition: The str value to base the retrieval of related records on.
        :returns: A list of PyRecordModel objects containing the ancestors of the root record.
        """
        anc_man = Manager.record_model_ancestor_manager(context=self.context)
        # Use a set when actually grabbing the related records to ensure we don't have duplicates grabbed.
        related_data_types: set[str] = set(self.get_related_record_types(label_definition))
        ancestors: list[PyRecordModel] = list()
        for data_type in related_data_types:
            ancestors.extend(list(anc_man.get_ancestors_of_type(root_record, data_type)))
        return ancestors

    @staticmethod
    def get_related_record_types(label_definition: str) -> list[str]:
        """
        Returns all data types from related record macros.

        :param label_definition: str value of structured label definition to scan for related record macros
        :returns: a list of the related data types referenced in the structured label definition, in str values.
        """
        return re.findall(r"\[(\w+)\.\w+]", label_definition)

    @staticmethod
    def run_macro_replacements(label_text: str, macro_values: Dict[str, list[str]]):
        """
        Replaces the content in label_text using the macro_values dictionary. The keys of macro_values are the macros
        in the label text to replace, and the list[str] values will be comma delimited to form the replacement.

        :param label_text: The input text to run replacements for.
        :param macro_values: The replacements to make within the label_text.
        :returns: The label_text str with macros replaced.
        """
        for macro in macro_values.keys():
            values: list[str] = list(set(macro_values.get(macro, [])))  # Convert to set for uniqueness, then back to list
            delimited_values = ", ".join(values)
            label_text = label_text.replace(macro, delimited_values)
        return label_text

    @staticmethod
    def blank_macros(label_text: str):
        """
        Converts all empty macros into empty strings, in case macro processing doesn't match them for some reason.

        :param label_text: the text to check for macros.
        """
        return re.sub(r"\[[.\w]+]", "", label_text)


class TakedaLabelPageTemplate(PageTemplate):
    NUM_DOWN = 17
    NUM_ACROSS = 5
    TOP_MARGIN = 0.24  # inches
    SIDE_MARGIN = 0.77  # inches
    VERTICAL_PITCH = 0.63  # inches
    HORIZONTAL_PITCH = 1.40  # inches
    LABEL_WIDTH = 1.28  # inches
    LABEL_HEIGHT = 0.50  # inches

    def __init__(self):
        content = []
        # Build frames, row by row
        for y_down in range(self.NUM_DOWN, 0, -1):  # Iterate downwards
            y_val = self.TOP_MARGIN + (y_down - 1) * self.VERTICAL_PITCH
            for x_across in range(0, self.NUM_ACROSS):
                x_val = self.SIDE_MARGIN + x_across * self.HORIZONTAL_PITCH
                content.append(
                    frames.Frame(
                        x_val * inch,
                        y_val * inch,
                        self.LABEL_WIDTH * inch,
                        self.LABEL_HEIGHT * inch,
                        leftPadding=0,
                        bottomPadding=0,
                        rightPadding=0,
                        topPadding=0
                     )
                )

        PageTemplate.__init__(self, id="test", frames=content, pagesize=letter)

    def blank_labels(self, start_row=1, start_column=1):
        return int(self.NUM_ACROSS) * (int(start_row) - 1) + (int(start_column) - 1)


class LabelPage:
    """ A Utility class to help with the construction of label pages PDFs. """
    buffer: BytesIO
    document: BaseDocTemplate
    objects: List
    label_definition: C_TakedaLabelDefinitionModel
    stylesheet: StyleSheet1
    context: SapioWebhookContext
    macro_man: LabelMacroManager

    def __init__(self, context: SapioWebhookContext,  definition: C_TakedaLabelDefinitionModel, start_row: int = 0, start_column: int = 1):
        """
        Requires context to make data type checks when formatting fields.

        :param context: The sapio webhook context for making necessary queries when compiling label data.
        :param definition: The label definition to use when formatting the data.
        :param start_row: 1 based value indicating which row to start printing labels in. The first row will be 1.
        :param start_column: 1 based value indicating which row to start printing labels in. The first column will be 1.
        """
        self.label_definition = definition
        self.context = context
        self.macro_man = LabelMacroManager(context)

        # Initialize empty buffer, document, and empty objects list.
        self.buffer = BytesIO()
        self.document = BaseDocTemplate(
            filename=self.buffer, author="takdev", title="labels"
        )
        self.objects = list()

        # Create our template, and add it to the document.
        template = TakedaLabelPageTemplate()
        self.document.addPageTemplates(template)

        # Calculate the total blank labels based on the start row and start column.
        rows_to_skip = (start_row - 1)
        columns_to_skip = (start_column - 1)
        blank_labels: int = (rows_to_skip * template.NUM_ACROSS) + columns_to_skip

        # Iterate over how many blank labels there are, and append empty frames.
        for _ in range(blank_labels):
            self.objects.append(FrameBreak())

        # build the style sheet.
        registerFont(TTFont("Arial", "Arial.ttf"))
        registerFont(TTFont("ArialBD", "ArialBD.ttf"))
        self.stylesheet = getSampleStyleSheet()
        style = {
            "name": "SampleLabel",
            "fontName": "Arial",
            "fontSize": 5,
            "leading": 5,
            "leftIndent": 5,
            "alignment": 1, # centered
        }
        self.stylesheet.add(ParagraphStyle(**style))

    def add_label(self, root_record: PyRecordModel, copies=1):
        """
        Formats sample info into a vial label

        :param root_record: A list of sapio record models, which will have data matched to macros
        :param copies: # of labels to print. Defaults to 1.
        :param root_data_type: The data type considered as "root" when replacing macros. Defaults to Sample.
        """
        # Grab the structured definition.
        label_text = self.label_definition.get_C_LabelStructureDefinition_field()

        # Create a collection of all related records.
        all_records = [root_record]
        all_records.extend(
            self.macro_man.get_related_records(
                root_record, self.label_definition.get_C_LabelStructureDefinition_field()))

        # Replace non-root record field macros. format: [[DataTypeName][DataFieldName]],
        # run the replacements before searching for root macros, to prevent false matches.
        related_record_macros = self.macro_man.compute_related_record_replacements(label_text, all_records)
        label_text = self.macro_man.run_macro_replacements(label_text, related_record_macros)

        # Replace root record field macros. Format: [DataFieldName]
        root_record_macros = self.macro_man.compute_root_record_replacements(label_text, root_record)
        label_text = self.macro_man.run_macro_replacements(label_text, root_record_macros)

        # All the other macros have had a chance. blank out what isn't found.
        label_text = self.macro_man.blank_macros(label_text)

        # Handle converting new lines to break characters for html.
        label_text = label_text.replace("\n", "<br />")

        # Handle converting bold tags to font tags with arial bold.
        label_text = label_text.replace("<b>", "<font name='ArialBD'>")
        label_text = label_text.replace("</b>", "</font>")

        for _ in range(copies):
            self.objects.append(
                paragraph.Paragraph(label_text, self.stylesheet["SampleLabel"])
            )
            self.objects.append(FrameBreak())

    def output(self) -> BytesIO:
        # always have a trailing FrameBreak - pop it off
        if len(self.objects) > 0:
            self.objects.pop()
        self.document.build(self.objects)
        self.buffer.seek(0)
        return self.buffer

    def load_related_records(self, records: List[WrappedRecordModel]):
        """
        Uses the utility method for loading related records based on related record macros, passing in this pages
        label definition.
        """
        self.macro_man.load_related_records(
            records, self.label_definition.get_C_LabelStructureDefinition_field())


class LabelUtil:
    """
    A utility class for functions related to labels.
    """

    PDF_POPUP_LABEL_START_ROW = "LabelStartRow"
    PDF_POPUP_LABEL_START_COLUMN = "LabelStartColumn"
    PDF_POPUP_NUM_LABELS_FIELD = "NumLabels"
    PDF_POPUP_DATATYPE = "LabelPrintPDFPopup"
    """ All of the constants needed to get data from the popup. """

    rec_handler: RecordHandler
    """ The record handler to use for querying models. """

    sapio_user: SapioUser
    """ The sapio user to initializing any managers as needed. """

    def __init__(self, user: UserIdentifier):
        """ Acceps either context or user object to initialize the record handler. """
        self.rec_handler = RecordHandler(user)
        self.sapio_user = AliasUtil.to_sapio_user(user)

    def get_takeda_label_definition(self, label_name: str) -> C_TakedaLabelDefinitionModel:
        """
        Retrieves the Label configuration with the given name. Displays an error to the user if one is not found
        or if there are multiple configurations found with this name.
        """
        matched_configurations: List[C_TakedaLabelDefinitionModel] = self.rec_handler.query_models(C_TakedaLabelDefinitionModel, C_TakedaLabelDefinitionModel.C_NAME__FIELD_NAME.field_name,[label_name])
        if len(matched_configurations) < 1:
            raise SapioUserErrorException("No Label Definition was found for \""+label_name+"\". "
                                            "Contact an administrator to ensure this is configured before printing labels.")
        if len(matched_configurations) > 1:
            raise SapioUserErrorException("Multiple Label Definitions were found for \""+label_name+"\". "
                                        "Please contact an administrator to ensure only one configuration exists with "
                                        "this name before printing labels.")
        return matched_configurations.pop()

    def prompt_for_label_details(self) -> Dict[str, Any]:
        """
        TODO: Return a pojo instead.
        Displays a popup with 3 fields to the user.
        - One field is for how many labels to print,
        - One field for the starting row position
        - One field for the starting column position
        """

        # Set up the number of labels field definition.
        num_labels_field: VeloxIntegerFieldDefinition = VeloxIntegerFieldDefinition(self.PDF_POPUP_DATATYPE, self.PDF_POPUP_NUM_LABELS_FIELD, "Number of Labels", 0)
        num_labels_field.editable = True
        num_labels_field.default_value = 1
        num_labels_field.min_value = 1
        num_labels_field.max_value = 29

        # Set up the "What row should the labels start on?" field definition.
        start_row_field: VeloxIntegerFieldDefinition = VeloxIntegerFieldDefinition(self.PDF_POPUP_DATATYPE, self.PDF_POPUP_LABEL_START_ROW, "Starting Row Position")
        start_row_field.editable = True
        start_row_field.default_value = 1
        start_row_field.min_value = 1
        start_row_field.max_value = TakedaLabelPageTemplate.NUM_DOWN

        # Set up the "What Column should the labels start on?" field definition.
        start_column_field: VeloxIntegerFieldDefinition = VeloxIntegerFieldDefinition(self.PDF_POPUP_DATATYPE, self.PDF_POPUP_LABEL_START_COLUMN, "Starting Column Position")
        start_column_field.editable = True
        start_column_field.default_value = 1
        start_column_field.min_value = 1
        start_column_field.max_value = TakedaLabelPageTemplate.NUM_ACROSS

        # Build the temp type and create the client callback request
        builder = FormBuilder(self.PDF_POPUP_DATATYPE, self.PDF_POPUP_DATATYPE, self.PDF_POPUP_DATATYPE)
        builder.add_field(num_labels_field)
        builder.add_field(start_row_field)
        builder.add_field(start_column_field)
        temp_type = builder.get_temporary_data_type()
        form_request = FormEntryDialogRequest("Label Printing", "", temp_type, width_in_pixels=250)

        # Run the actual prompt.
        results = ClientCallback(self.sapio_user).show_form_entry_dialog(form_request)

        # Handle cancellations
        if results is None:
            raise SapioUserCancelledException()
        num_labels: int | None = results.get(self.PDF_POPUP_NUM_LABELS_FIELD)
        if num_labels is None or num_labels < 1:
            raise SapioUserCancelledException()
        return results
