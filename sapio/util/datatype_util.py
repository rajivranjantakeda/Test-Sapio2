from sapiopylib.rest.pojo.datatype.DataTypeComponent import DataFormComponent
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext

from sapio.manager.manager_retrievals import Manager


class DataTypeUtil:

    @staticmethod
    def get_field_definitions_in_order(data_type_name: str, context: SapioWebhookContext) -> list[AbstractVeloxFieldDefinition]:
        """
        Retrieve field definitions for a specific data type in their layout-defined order.

        This method collects field definitions based on their arrangement in the default layout,
        sorting them according to tabs, components, and position orders. It ensures that fields
        are extracted in the precise sequence they appear in the user interface.

        Args:
            data_type_name (str): The name of the data type for which to retrieve field definitions.
            context (SapioWebhookContext): The webhook context providing access to data type resources.

        Returns:
            list[AbstractVeloxFieldDefinition]: An ordered list of field definitions matching
            the layout configuration, preserving their UI presentation sequence.

        Notes:
            - Empty layouts or data types with no fields return an empty list.
            - Fields are sorted based on tab order, component order, and position order.
            - Duplicate fields may be included if they appear multiple times in the layout.
        """
        data_type_manager = Manager.data_type_manager(context)

        field_defs_by_name = {
            field.data_field_name: field
            for field in data_type_manager.get_field_definition_list(data_type_name)
        }

        if not field_defs_by_name:
            return []

        default_layout = data_type_manager.get_default_layout(data_type_name)

        field_defs_in_order = []

        for tab in sorted(default_layout.get_data_type_tab_definition_list(), key=lambda x: x.tab_order):
            for component in sorted(tab.get_full_layout_component_list(), key=lambda x: x.order):
                if not isinstance(component, DataFormComponent):
                    continue

                for pos in sorted(component.positions, key=lambda x: x.order):
                    if pos.data_field_name not in field_defs_by_name:
                        continue

                    field = field_defs_by_name[pos.data_field_name]
                    field_defs_in_order.append(field)

        return field_defs_in_order