import re

from sapiopycommons.customreport.custom_report_builder import CustomReportBuilder
from sapiopycommons.customreport.term_builder import TermBuilder
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.DataRecord import DataRecord
from sapiopylib.rest.CustomReportService import CustomReportManager
from sapiopylib.rest.DataMgmtService import DataMgmtServer
from sapiopylib.rest.pojo.CustomReport import ReportColumn, RawReportTerm, RawTermOperation, CustomReportCriteria
from sapiopylib.rest.pojo.datatype.FieldDefinition import FieldType
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.DataTypeService import DataTypeManager

from sapio.enum.tags import DataFieldTags

KEY_FIELD: str = "C_OptionKey"
VALUE_FIELD: str = "C_OptionValue"


class DynamicSelection(CommonsWebhookHandler):
    """DynamicSelection is a subclass of CommonsWebhookHandler designed to handle dynamic selection logic
       based on specific field definitions and regex patterns within tags.
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        data_type_man: DataTypeManager = DataTypeManager(context.user)

        # Get the list of fields definitions.
        fields: list[AbstractVeloxFieldDefinition] = data_type_man.get_field_definition_list(context.data_type_name)

        search_datatype = None
        filter_field = None
        for field in fields:
            if field.data_field_name == context.data_field_name:
                # Set the tag and save a reference to the record id.
                tag: str = field.tag

                # Find matches
                matches = re.findall(DataFieldTags.DYNAMIC_SELECTION_LIST_TAG, tag)
                if matches:
                    search_datatype, filter_field = matches[0]
                    break
                else:
                    return SapioWebhookResult(False, "Dynamic Selection List field has not been configured correctly.")

        # Handle the case where the search_datatype and filter_field are not found.
        if not search_datatype or not filter_field:
            return SapioWebhookResult(False, "Unable to find dynamic selection criteria. Please contact a system administrator.")

        # Get the filter value from the current record. If we have a list of str values, convert it to a list for our search.
        filter_value = context.field_map.get(filter_field)
        if "," in filter_value:
            filter_value = filter_value.split(",")
            trimmed_values = list()
            for value in filter_value:
                trimmed_values.append(value.strip())
            filter_value = trimmed_values

        # Build a custom report to get the list of values.
        report_builder = CustomReportBuilder(search_datatype)
        report_builder.add_column(VALUE_FIELD, FieldType.STRING)
        filter_term: RawReportTerm = TermBuilder.is_term(search_datatype, KEY_FIELD, filter_value)
        report_builder.set_root_term(filter_term)

        # Run that report
        report_man: CustomReportManager = DataMgmtServer.get_custom_report_manager(context.user)
        custom_report = report_builder.build_report_criteria()
        result_table: list[list[str]] = report_man.run_custom_report(custom_report).result_table

        result: list[str] = []
        # If we get a result from the custom report.
        for result_row in result_table:
            result.append(result_row[0])

        return SapioWebhookResult(True, list_values=result)
