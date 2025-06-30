from typing import List, Optional, Dict

from sapiopycommons.eln.experiment_handler import ExperimentHandler
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.pojo.eln.ExperimentEntry import ExperimentEntry
from sapiopylib.rest.pojo.eln.protocol_template import ProtocolTemplateInfo
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.utils.recordmodel.PyRecordModel import PyRecordModel

from sapio.model.data_type_models import SampleModel, ELNSampleDetailModel


class CustomGrabberContext:
    """
    A pojo containing all the data collected when running generic custom grabber logic, so that it can be used with
    specific grabbers later.
    """
    def __init__(self, source_samples: Optional[List[SampleModel]] = None,  # The samples used to make sample details.
                 sample_step: ExperimentEntry = None,  # The entry that the samples were pulled from.
                 created_entries: Optional[List[ExperimentEntry]] = None,  # The entries created from this protocol.
                 experiment_handler: ExperimentHandler = None,  # The experiment handler from the prior execution.
                 created_sample_details_by_entry_id: Dict[int, List[PyRecordModel]] = None,  # The sample details.
                 protocol: ProtocolTemplateInfo = None,  # The protocol that was grabbed.
                 title: str = None,  # The title that was given, if any.
                 field_definitions: Dict[int, List[AbstractVeloxFieldDefinition]] = None  # ELN Field Definitions
                    ):
        self.source_samples = source_samples
        self.sample_step = sample_step
        self.created_entries = created_entries if created_entries is not None else []
        self.experiment_handler = experiment_handler
        self.created_sample_details_by_entry_id = created_sample_details_by_entry_id
        self.protocol = protocol
        self.title = title
        self.field_definitions = field_definitions


class CustomGrabberContextBuilder:
    """
    A builder for constructing CustomGrabberContext objects.
    """
    def __init__(self):
        self._source_samples = None
        self._sample_step = None
        self._created_entries = []
        self._experiment_handler = None
        self._sample_details = None
        self._protocol = None
        self._title = None
        self._webhook_context = None
        self._field_definitions = None

    def source_samples(self, source_samples: List[SampleModel]) -> 'CustomGrabberContextBuilder':
        self._source_samples = source_samples
        return self

    def sample_step(self, sample_step: ExperimentEntry) -> 'CustomGrabberContextBuilder':
        self._sample_step = sample_step
        return self

    def created_entries(self, created_entries: List[ExperimentEntry]) -> 'CustomGrabberContextBuilder':
        self._created_entries = created_entries
        return self

    def experiment_handler(self, experiment_handler: ExperimentHandler) -> 'CustomGrabberContextBuilder':
        self._experiment_handler = experiment_handler
        return self

    def sample_details(self, sample_details_by_entry_id: Dict[int, List[PyRecordModel]]) -> 'CustomGrabberContextBuilder':
        self._sample_details = sample_details_by_entry_id
        return self

    def protocol(self, protocol: ProtocolTemplateInfo) -> 'CustomGrabberContextBuilder':
        self._protocol = protocol
        return self

    def title(self, title: str) -> 'CustomGrabberContextBuilder':
        self._title = title
        return self

    def webhook_context(self, webhook_context: SapioWebhookContext) -> 'CustomGrabberContextBuilder':
        self._webhook_context = webhook_context
        return self

    def field_definitions(self, fields_by_entry_id: Dict[int, List[AbstractVeloxFieldDefinition]]):
        self._field_definitions = fields_by_entry_id

    def build(self) -> CustomGrabberContext:
        return CustomGrabberContext(
            source_samples=self._source_samples,
            sample_step=self._sample_step,
            created_entries=self._created_entries,
            experiment_handler=self._experiment_handler,
            created_sample_details_by_entry_id=self._sample_details,
            protocol=self._protocol,
            title=self._title,
            field_definitions=self._field_definitions
        )


