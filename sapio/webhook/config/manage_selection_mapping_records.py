from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.customreport.custom_report_builder import CustomReportBuilder
from sapiopycommons.customreport.term_builder import TermBuilder
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.DataTypeService import DataTypeManager
from sapiopylib.rest.PicklistService import PicklistManager
from sapiopylib.rest.pojo.CustomReport import CustomReport, CustomReportCriteria
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookDirective import CustomReportDirective
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapio.model.data_type_models import C_AssaysByProductModel


class ManageSelectionMappingRecords(CommonsWebhookHandler):
    """
    The ManageSelectionMappingRecords class is responsible for handling webhook events related to the management of 
    selection mapping records. It queries the database for a specific picklist, prompts the user to select a data type 
    from the list, and then searches for records of the selected type. The results are then displayed to the user.
    """
    PICKLIST_NAME = "Dynamic Selection List Mapping Data Types"
    RECORD_ID_FIELD = "RecordId"

    REPORT_FIELDS = [
        C_AssaysByProductModel.C_OPTIONKEY__FIELD_NAME,
        C_AssaysByProductModel.C_OPTIONVALUE__FIELD_NAME,
        C_AssaysByProductModel.CREATEDBY__FIELD_NAME,
        C_AssaysByProductModel.DATECREATED__FIELD_NAME,
        C_AssaysByProductModel.VELOXLASTMODIFIEDBY__FIELD_NAME,
        C_AssaysByProductModel.VELOXLASTMODIFIEDDATE__FIELD_NAME
    ]

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        """
        Executes the webhook logic.

        Args:
            context (SapioWebhookContext): The webhook context with user and session details.

        Returns:
            SapioWebhookResult: Result containing directives or success status.
        """
        callback = CallbackUtil(context)
        try:
            # Retrieve picklist entries for mapping data types.
            picklist = PicklistManager(context.user).get_picklist(self.PICKLIST_NAME)
            if not picklist:
                return self._display_error(callback, f"Picklist '{self.PICKLIST_NAME}' does not exist.")

            selection_mapping_data_types = picklist.entry_list
            if not selection_mapping_data_types:
                return self._display_error(callback, f"Picklist '{self.PICKLIST_NAME}' is empty.")

            # Map display names to data type names.
            data_type_map = self._build_data_type_map(context, selection_mapping_data_types)
            if not data_type_map:
                return SapioWebhookResult(passed=True)

            # Prompt the user to select a data type.
            user_choice = self._prompt_user_selection(context, list(data_type_map.keys()))
            if not user_choice:
                return SapioWebhookResult(passed=True)

            chosen_display_name = user_choice.pop()
            chosen_data_type = data_type_map[chosen_display_name]

            # Generate and run a custom report for the chosen data type.
            custom_report = self._build_custom_report(chosen_data_type)

            return SapioWebhookResult(passed=True, directive=CustomReportDirective(custom_report))
        except Exception as e:
            # Handle unexpected errors gracefully.
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

    def _build_data_type_map(self, context: SapioWebhookContext, data_types: list[str]) -> dict[str, str]:
        """
        Builds a mapping of display names to data type names.

        Args:
            context (SapioWebhookContext): The webhook context.
            data_types (list[str]): List of data type names.

        Returns:
            dict[str, str]: Mapping of display names to data type names.
        """
        data_type_manager = DataTypeManager(context.user)
        return {
            data_type_def.display_name: data_type_def.get_data_type_name()
            for data_type in data_types
            if (data_type_def := data_type_manager.get_data_type_definition(data_type))
        }

    def _prompt_user_selection(self, context: SapioWebhookContext, options: list[str]) -> list[str]:
        """
        Prompts the user to select a data type.

        Args:
            context (SapioWebhookContext): The webhook context.
            options (list[str]): Display names of data types.

        Returns:
            list[str]: User's selected options.
        """
        callback = CallbackUtil(context)
        return callback.list_dialog(
            title="Select Data Type",
            options=options,
            multi_select=False
        )

    def _build_custom_report(self, data_type: str) -> CustomReportCriteria:
        """
        Runs a custom report for the specified data type.

        Args:
            context (SapioWebhookContext): The webhook context.
            data_type (str): The selected data type.

        Returns:
            CustomReport: Results of the custom report.
        """
        report_builder = CustomReportBuilder(data_type)
        for field in self.REPORT_FIELDS:
            report_builder.add_column(
                field.field_name,
                field_type=field.field_type
            )
        filter_term = TermBuilder.not_term(data_type=data_type, field=self.RECORD_ID_FIELD, value=0)
        report_builder.set_root_term(filter_term)

        return report_builder.build_report_criteria()
