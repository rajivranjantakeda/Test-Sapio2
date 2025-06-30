from datetime import datetime
from typing import List

from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.recordmodel.PyRecordModel import PyRecordModel
from sapiopylib.rest.utils.recordmodel.RelationshipPath import RelationshipPath

from sapio.helper.takeda_data_type_helper import TakedaDataTypeHelper
from sapio.model.data_type_models import SampleModel, C_CellCultureMeasurementsModel, ELNSampleDetailModel
from sapio.model.eln_classes import ELNSampleDetail


class DaysSinceDayZero(CommonsWebhookHandler):
    """
    Calculate the days since seeding time on the offline and online records. Then set it on the records within the
    context of this webhook (saved records).

    Seeding time is set on the first entry of the bioreactor building block, on submission of which the aliquots, that
    go onto the bioreactor, are created. This would be an editable field that is presently called Timestamp.
    """

    FIELD_TIMESTAMP = C_CellCultureMeasurementsModel.C_TIMESTAMP__FIELD_NAME.field_name
    FIELD_DAYS_SINCE_D0 = C_CellCultureMeasurementsModel.C_DAYSSINCED0__FIELD_NAME.field_name
    FIELD_DAY = C_CellCultureMeasurementsModel.C_DAY__FIELD_NAME.field_name

    FIELD_IDENTIFYING_SEEDING_DETAIL: str = ELNSampleDetail.PASSAGING_TO_STEP
    FIELD_SEEDING_DATE: str = ELNSampleDetail.TIMESTAMP

    data_type_helper: TakedaDataTypeHelper

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        self.data_type_helper = TakedaDataTypeHelper(self.context)

        all_records: list[PyRecordModel] = self.inst_man.add_existing_records(context.data_record_list)

        if len(all_records) < 1:
            # Early return if no records are present.
            return SapioWebhookResult(True)

        # Load path to all the other measurement records.
        path_to_other_records: RelationshipPath = RelationshipPath().parent_type(SampleModel).parent_type(SampleModel).child_type(ELNSampleDetailModel)
        self.rel_man.load_path(all_records, path_to_other_records)

        for record in all_records:

            seeding_time: int = self.get_seeding_time(record)

            if not seeding_time:
                continue

            measurement_timestamp = record.get_field_value(self.FIELD_TIMESTAMP)

            # Get the elapsed time since then.
            oldest_datetime = datetime.fromtimestamp(seeding_time / 1000)
            measurement_datetime = datetime.fromtimestamp(measurement_timestamp / 1000)
            time_difference = (measurement_datetime - oldest_datetime)

            # Set the value of the oldest timestamp as Days since D0.
            days_since_d0 = (time_difference.total_seconds() / (24 * 3600))

            # Set the value of the oldest timestamp as Days since D0.
            record.set_field_value(self.FIELD_DAYS_SINCE_D0, days_since_d0)

            # Calculate the difference in days.
            difference_in_days = time_difference.days

            # Set the ceil of that value as Day.
            record.set_field_value(self.FIELD_DAY, difference_in_days)

        # Commit changes.
        self.rec_man.store_and_commit()

        # Return.
        return SapioWebhookResult(True)

    def get_seeding_time(self, record) -> int | None:
        """
        Seeding time is set on the Sample Detail records that are used to create aliquot samples, which go on the
        bioreactor (seeded onto the bioreactor).

        Note: Relationships are expected to have been loaded by now.

        :param record: Offline or Online record

        :return: A seeding time as set by the user.
        """

        latest_sample_detail_date: int = 0
        seeding_date: int | None = None

        # First get parent records from the current offline or online record, which is added under the sample on the bioreactor
        related_samples: List[PyRecordModel] = record.get_parents_of_type(SampleModel.DATA_TYPE_NAME)

        if not related_samples:
            return None

        # There should only be one
        for related_sample in related_samples:

            # Get the parent samples from which the sample on the bioreactor was created
            source_samples: List[PyRecordModel] = related_sample.get_parents_of_type(SampleModel.DATA_TYPE_NAME)

            if not source_samples:
                return None

            # Should only be one
            for source_sample in source_samples:

                # Get sample detail records that would have been used to create the aliquot sample on the bioreactor
                sample_details: List[PyRecordModel] = source_sample.get_children_of_type(ELNSampleDetailModel.DATA_TYPE_NAME)

                if not sample_details:
                    return None

                # There will be multiple of these. We need to identify which one to use by looking for a key field, which is
                # PassagingToStep. Selecting this field because it is unique to the entry on submit of which the aliquot
                # is created, and which contains the Timestamp field, recording the seeding time.
                for sample_detail in sample_details:

                    # Check for the key field and for the latest version of the sample detail. This is to handle cases
                    # where the same sample might be processed more than once
                    if not self.should_use_sample_detail(sample_detail, latest_sample_detail_date):
                        continue

                    seeding_time: int = sample_detail.get_field_value(self.FIELD_SEEDING_DATE)

                    if seeding_time:
                        latest_sample_detail_date = sample_detail.get_field_value(ELNSampleDetail.DATE_CREATED)
                        seeding_date = seeding_time

        return seeding_date


    def should_use_sample_detail(self, sample_detail: PyRecordModel, latest_sample_detail_date: int) -> bool:
        """
        Check for the key field on the data type, and on the date of this record to ensure it's the latest one.
        :param sample_detail:
        :param latest_sample_detail_date:
        :return:
        """

        if not self.data_type_helper.is_field_in_data_type(sample_detail.data_type_name, self.FIELD_IDENTIFYING_SEEDING_DETAIL):
            return False

        if not self.data_type_helper.is_field_in_data_type(sample_detail.data_type_name, self.FIELD_SEEDING_DATE):
            return False

        if latest_sample_detail_date > sample_detail.get_field_value(ELNSampleDetail.DATE_CREATED):
            return False

        return True