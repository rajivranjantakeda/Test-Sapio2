from sapiopylib.rest.DataTypeService import DataTypeManager
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext

from sapio.manager.manager_retrievals import Manager


class TakedaDataTypeHelper:
    """
    A helper class to manage data type field definitions within the Sapio environment.

    Attributes:
        context (SapioWebhookContext | None): The webhook context for the current Sapio session.
        data_type_man (DataTypeManager | None): Manages the interaction with Sapio's data type definitions.
        data_type_to_fields (dict[str, dict[str, AbstractVeloxFieldDefinition]]):
            A cache for field definitions, organized by data type name and field name.
    """

    context: SapioWebhookContext | None = None
    data_type_man: DataTypeManager | None = None

    data_type_to_fields: dict[str, dict[str, AbstractVeloxFieldDefinition]] = dict()

    def __init__(self, context: SapioWebhookContext):
        self.context = context
        self.data_type_man = Manager.data_type_manager(context)

    def is_field_in_data_type(self, data_type_name: str, field_name: str) -> bool:
        """
        Checks if a specific field exists within a given data type.

        Args:
            data_type_name (str): The name of the data type to query.
            field_name (str): The name of the field to check for.

        Returns:
            bool: True if the field exists within the data type, otherwise False.
        """
        # Check if the data type is already cached
        if self.data_type_to_fields.__contains__(data_type_name):
            return self.data_type_to_fields[data_type_name].__contains__(field_name)

        # Retrieve field definitions for the data type and cache them
        field_list: list[AbstractVeloxFieldDefinition] = self.data_type_man.get_field_definition_list(data_type_name)
        field_mapping: dict[str, AbstractVeloxFieldDefinition] = dict()

        for field in field_list:
            field_mapping[field.data_field_name] = field

        self.data_type_to_fields[data_type_name] = field_mapping

        return self.data_type_to_fields[data_type_name].__contains__(field_name)
