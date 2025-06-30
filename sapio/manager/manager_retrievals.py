from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.CustomReportService import CustomReportManager
from sapiopylib.rest.DataMgmtService import DataMgmtServer
from sapiopylib.rest.DataRecordManagerService import DataRecordManager
from sapiopylib.rest.DataTypeService import DataTypeManager
from sapiopylib.rest.ELNService import ElnManager
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.utils.recordmodel.RecordModelManager import (
    RecordModelInstanceManager,
    RecordModelManager,
    RecordModelRelationshipManager,
)
from sapiopylib.rest.utils.recordmodel.ancestry import RecordModelAncestorManager


class Manager:

    @staticmethod
    def data_record_manager(context: SapioWebhookContext) -> DataRecordManager:
        return context.data_record_manager

    @staticmethod
    def instance_manager(webhook_handler: CommonsWebhookHandler) -> RecordModelInstanceManager:
        return webhook_handler.inst_man

    @staticmethod
    def eln_manager(context: SapioWebhookContext) -> ElnManager:
        return context.eln_manager

    @staticmethod
    def record_model_manager(context: SapioWebhookContext) -> RecordModelManager:
        return RecordModelManager(context.user)

    @staticmethod
    def record_model_instance_manager(context: SapioWebhookContext) -> RecordModelInstanceManager:
        return Manager.record_model_manager(context).instance_manager

    @staticmethod
    def custom_report_manager(context: SapioWebhookContext) -> CustomReportManager:
        return DataMgmtServer.get_custom_report_manager(context.user)

    @staticmethod
    def record_model_relationship_manager(context: SapioWebhookContext) -> RecordModelRelationshipManager:
        return Manager.record_model_manager(context).relationship_manager

    @staticmethod
    def data_type_manager(context: SapioWebhookContext) -> DataTypeManager:
        return DataMgmtServer.get_data_type_manager(context.user)

    @staticmethod
    def record_model_ancestor_manager(context: SapioWebhookContext) -> RecordModelAncestorManager:
        return RecordModelAncestorManager(Manager.record_model_manager(context))

    @staticmethod
    def experiment_handler(context: SapioWebhookContext) -> ExperimentHandler:
        return ExperimentHandler(context)

    @staticmethod
    def record_handler(context: SapioWebhookContext) -> RecordHandler:
        return RecordHandler(context)
