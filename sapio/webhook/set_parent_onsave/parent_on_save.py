import re
from typing import List, Dict

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.general.exceptions import SapioUserCancelledException
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.DataTypeService import DataTypeManager
from sapiopylib.rest.pojo.DataRecord import DataRecord
from sapiopylib.rest.pojo.datatype.DataType import DataTypeDefinition
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.autopaging import QueryAllRecordsOfTypeAutoPager
from sapiopylib.rest.utils.recordmodel.PyRecordModel import PyRecordModel
from sapiopylib.rest.utils.recordmodel.RecordModelUtil import RecordModelUtil


class AddParentOnSave(CommonsWebhookHandler):
    """
    This webhook handler is intended to relate new records of a given data type to an individual parent record. This
    webhook should be invoked by an onsave rule witht he following format:
        " When the {DataType} is new...."

    Requirement Documentation: https://onetakeda.atlassian.net/browse/ELNMSLAB-457
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        # 1. Determine the data type of the new records.
        data_type: str = context.data_type_name

        # 2. Check the tags on the data type.
        data_type_def: DataTypeDefinition = DataTypeManager(context.user).get_data_type_definition(data_type)
        description = data_type_def.description
        matches: List[str] = re.findall(r"<!--\s*WHEN\s*NEW\s*ADD\s*TO:\s*(\w+)\s*-->", description)
        if len(matches) < 1:
            # Early return if tag is not found.
            return SapioWebhookResult(True)

        # 3. Get the data type name of the parent type.
        parent_type: str = matches.pop()

        # 4. Get all records with that data type name
        pager = QueryAllRecordsOfTypeAutoPager(parent_type, context.user)
        all_potential_parent_records: List[DataRecord] = pager.get_all_at_once()
        potential_parents: List[PyRecordModel] = self.inst_man.add_existing_records(all_potential_parent_records)
        if len(potential_parents) < 1:
            # Early return if no potential parents are found.
            return SapioWebhookResult(True)

        # 5. If there are multiple, attempt to prompt user for selection.
        selected_parent = potential_parents.pop()

        # 6. When there is one selected parent, relate the new records as children of the new parent.
        new_records: List[PyRecordModel] = self.inst_man.add_existing_records(context.data_record_list)
        selected_parent.add_children(new_records)

        # 7. Commit changes.
        self.rec_man.store_and_commit()

        # 8. Return.
        return SapioWebhookResult(True)
