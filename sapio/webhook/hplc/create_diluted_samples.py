from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.recordmodel.properties import Child

from sapio.model.data_type_models import C_DilutedSampleModel, SampleModel, ELNSampleDetailModel
from sapio.webhook.hplc.entries import SampleDilutionFields


class CreateDilutedSamplesForHPLC(CommonsWebhookHandler):

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:

        self.delete_existing_diluted_samples()

        experiment_records: list[ELNSampleDetailModel] = self.get_experiment_records(context)
        grouped_records: dict[str, list[ELNSampleDetailModel]] = self.group_records_by_sample_id(experiment_records)
        latest_records: list[ELNSampleDetailModel] = self.get_latest_records(grouped_records)
        diluted_samples = self.create_diluted_samples(latest_records)
        self.rec_man.store_and_commit()

        self.exp_handler.set_step_records("Diluted Samples", diluted_samples)

        return SapioWebhookResult(True, "Diluted Samples created successfully.")

    def get_experiment_records(self, context: SapioWebhookContext) -> list[ELNSampleDetailModel]:
        """
        Fetches records from the experiment entry.

        :param context: The webhook context containing the experiment entry.
        :return: List of experiment records.
        """
        return self.exp_handler.get_step_models(context.experiment_entry.entry_name, ELNSampleDetailModel)

    def group_records_by_sample_id(self, experiment_records: list[ELNSampleDetailModel]) -> dict[str, list[ELNSampleDetailModel]]:
        """
        Groups experiment records by the SAMPLE_ID field.

        :param experiment_records: List of experiment records.
        :return: Dictionary grouping records by SAMPLE_ID.
        """
        grouped_records: dict[str, list[ELNSampleDetailModel]] = {}

        for record in experiment_records:
            sample_id = record.get_SampleId_field()

            if sample_id not in grouped_records:
                grouped_records[sample_id] = []

            grouped_records[sample_id].append(record)

        return grouped_records

    def get_latest_records(self, grouped_records: dict[str, list[ELNSampleDetailModel]]) -> list[ELNSampleDetailModel]:
        """
        Identifies the latest record in each group based on the DateCreatedField.

        :param grouped_records: Dictionary of records grouped by SAMPLE_ID.
        :return: List of the latest records from each group.
        """
        latest_records: list[ELNSampleDetailModel] = []

        for sample_id, records in grouped_records.items():
            latest_record = max(records, key=lambda rec: rec.get_DateCreated_field())
            latest_records.append(latest_record)

        return latest_records

    def create_diluted_samples(self, latest_records) -> list[C_DilutedSampleModel]:
        """
        Creates C_DilutedSampleModel instances for each of the latest records.

        :param latest_records: List of the latest records from grouped data.
        :return: List of created C_DilutedSampleModel instances.
        """

        # Load sample parents
        self.rel_man.load_parents_of_type(
            wrapped_records=latest_records,
            parent_wrapper_type=SampleModel
        )

        diluted_samples: list[C_DilutedSampleModel] = []

        for record in latest_records:
            parent_sample = record.get_parent_of_type(SampleModel)
            if parent_sample:
                diluted_sample: C_DilutedSampleModel = parent_sample.add(Child.create(C_DilutedSampleModel))
                diluted_samples.append(diluted_sample)

                diluted_sample.set_C_SampleId_field(record.get_field_value(SampleDilutionFields.SAMPLE_ID))
                diluted_sample.set_C_OtherSampleId_field(record.get_field_value(SampleDilutionFields.SAMPLE_NAME))
                diluted_sample.set_C_DilutionFactor_field(record.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
                diluted_sample.set_C_Concentration_field(record.get_field_value(SampleDilutionFields.TARGET_CONCENTRATION))
                diluted_sample.set_C_ConcentrationUnits_field("mg/mL")
                diluted_sample.set_C_Volume_field(record.get_field_value(SampleDilutionFields.TOTAL_VOLUME))
                diluted_sample.set_C_VolumeUnits_field("mL")

        return diluted_samples

    def delete_existing_diluted_samples(self):
        """
        Mark the existing records for deletion, in case we are resubmitting.
        """
        existing_diluted_sample_records: list[C_DilutedSampleModel] = self.exp_handler.get_step_models("Diluted Samples", C_DilutedSampleModel)

        for existing_record in existing_diluted_sample_records:
            existing_record.delete()
