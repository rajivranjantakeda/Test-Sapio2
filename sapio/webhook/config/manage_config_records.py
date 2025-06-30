from abc import ABC, abstractmethod

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.customreport.custom_report_builder import CustomReportBuilder
from sapiopycommons.customreport.term_builder import TermBuilder
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookDirective import CustomReportDirective
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.model.data_type_models import C_PurificationYieldConfigModel, C_PIFieldMappingModel, C_TakedaLabelDefinitionModel
from sapio.util.datatype_util import DataTypeUtil


class ManageConfigRecords(CommonsWebhookHandler, ABC):

    @abstractmethod
    def get_data_type(self):
        pass

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        callback = CallbackUtil(context)
        try:
            # Step 1: Get data type name and retrieve field definitions in the correct order
            data_type_name = self.get_data_type()
            field_defs_in_order = DataTypeUtil.get_field_definitions_in_order(data_type_name, context)

            if not field_defs_in_order:
                return self._display_error(callback, f"No fields found for data type: {data_type_name}")

            # Step 2: Build a custom report containing all obtained fields
            report_builder = CustomReportBuilder(data_type_name)
            for field in field_defs_in_order:
                report_builder.add_column(field.data_field_name, field_type=field.data_field_type)

            # Add a filter term to the report
            filter_term = TermBuilder.not_term(data_type=data_type_name, field="RecordId", value=0)
            report_builder.set_root_term(filter_term)

            custom_report_criteria = report_builder.build_report_criteria()

            # Step 3: Direct user to the built CustomReportCriteria object
            return SapioWebhookResult(
                passed=True,
                directive=CustomReportDirective(custom_report_criteria)
            )

        except Exception as e:
            return self._display_error(callback, f"An unexpected error occurred: {str(e)}")

    def _display_error(self, callback: CallbackUtil, message: str) -> SapioWebhookResult:
        """
        Displays an error message to the user and returns a failed webhook result.

        Args:
            callback (CallbackUtil): The callback utility to show dialogs.
            message (str): The error message to display.

        Returns:
            SapioWebhookResult: A failed webhook result.
        """
        callback.ok_dialog("Error", message)
        return SapioWebhookResult(passed=False)

class ManagePurificationYieldConfigs(ManageConfigRecords):
    def get_data_type(self):
        return C_PurificationYieldConfigModel.DATA_TYPE_NAME

class ManagePIFieldMappingConfigs(ManageConfigRecords):
    def get_data_type(self):
        return C_PIFieldMappingModel.DATA_TYPE_NAME

class ManageTakedaLabelDefinitions(ManageConfigRecords):
    def get_data_type(self):
        return C_TakedaLabelDefinitionModel.DATA_TYPE_NAME
