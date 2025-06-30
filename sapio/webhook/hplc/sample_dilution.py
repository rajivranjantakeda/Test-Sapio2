from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult

from sapiopylib.rest.utils.Protocols import ElnEntryStep
from sapio.model.data_type_models import ELNSampleDetailModel
from sapio.webhook.hplc.entries import SampleDilutionFields


class HPLCSampleDilution(CommonsWebhookHandler):
    """
    This webhook is used to calculate the dilution factor, sample volume, volume of MPA, and target concentration.
    """
    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Get the current table entry.
        dilution_entry_step: ElnEntryStep = self.exp_handler.get_step(context.active_step.get_name())

        # Get the sample details from the current table entry.
        sample_details: list[ELNSampleDetailModel] = self.exp_handler.get_step_models(dilution_entry_step, ELNSampleDetailModel)

        for detail in sample_details:
            # Retrieve necessary field values from the sample details
            target_concentration = detail.get_field_value(SampleDilutionFields.TARGET_CONCENTRATION)
            total_volume = detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME)
            sample_volume = detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME)
            dilution_factor = detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR)

            # Calculate missing values based on available data
            if target_concentration and total_volume:
                # Calculate dilution factor and sample volume when target concentration and total volume are known
                detail.set_field_value(SampleDilutionFields.DILUTION_FACTOR, detail.get_field_value(SampleDilutionFields.ESTIMATED_CONCENTRATION) / detail.get_field_value(SampleDilutionFields.TARGET_CONCENTRATION))
                detail.set_field_value(SampleDilutionFields.SOURCE_VOLUME, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) / detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
                detail.set_field_value(SampleDilutionFields.VOLUME_OF_MPA, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) - detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME))
            elif sample_volume and total_volume:
                # Calculate volume of MPA and dilution factor when sample volume and total volume are known
                detail.set_field_value(SampleDilutionFields.VOLUME_OF_MPA, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) - detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME))
                detail.set_field_value(SampleDilutionFields.DILUTION_FACTOR, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) / detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME))
                detail.set_field_value(SampleDilutionFields.TARGET_CONCENTRATION, detail.get_field_value(SampleDilutionFields.ESTIMATED_CONCENTRATION) / detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
            elif sample_volume and target_concentration:
                # Calculate dilution factor and total volume when sample volume and target concentration are known
                detail.set_field_value(SampleDilutionFields.DILUTION_FACTOR, detail.get_field_value(SampleDilutionFields.ESTIMATED_CONCENTRATION) / detail.get_field_value(SampleDilutionFields.TARGET_CONCENTRATION))
                detail.set_field_value(SampleDilutionFields.TOTAL_VOLUME, detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME) * detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
                detail.set_field_value(SampleDilutionFields.VOLUME_OF_MPA, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) - detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME))
            elif dilution_factor and total_volume:
                # Calculate target concentration and sample volume when dilution factor and total volume are known
                detail.set_field_value(SampleDilutionFields.TARGET_CONCENTRATION, detail.get_field_value(SampleDilutionFields.ESTIMATED_CONCENTRATION) / detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
                detail.set_field_value(SampleDilutionFields.SOURCE_VOLUME, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) / detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
                detail.set_field_value(SampleDilutionFields.VOLUME_OF_MPA, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) - detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME))
            elif dilution_factor and sample_volume:
                # Calculate total volume and target concentration when dilution factor and sample volume are known
                detail.set_field_value(SampleDilutionFields.TOTAL_VOLUME, detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME) * detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))
                detail.set_field_value(SampleDilutionFields.VOLUME_OF_MPA, detail.get_field_value(SampleDilutionFields.TOTAL_VOLUME) - detail.get_field_value(SampleDilutionFields.SOURCE_VOLUME))
                detail.set_field_value(SampleDilutionFields.TARGET_CONCENTRATION, detail.get_field_value(SampleDilutionFields.ESTIMATED_CONCENTRATION) / detail.get_field_value(SampleDilutionFields.DILUTION_FACTOR))

        # All done.
        self.rec_man.store_and_commit()

        return SapioWebhookResult(True, "Sample dilution successful")
