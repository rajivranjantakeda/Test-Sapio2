from typing import Any, Dict, List

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopycommons.webhook.webhook_handlers import CommonsWebhookHandler
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext
from sapiopylib.rest.pojo.webhook.WebhookResult import SapioWebhookResult
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import RecordModelWrapperUtil

from sapio.model.data_type_models import C_TakedaLabelDefinitionModel, SampleModel, ELNSampleDetailModel, \
    C_TestAliquotModel
from sapio.webhook.label_printing.base_label import LabelPage, LabelUtil

LEXINGTON_LABEL_ON_A_PDF = "Lexington sample label on a PDF"
INTERMEDIATE_LABEL_ON_A_PDF = "Lexington intermediate purification sample label on a PDF"
TEST_ALIQUOT_LABEL_ON_A_PDF = "Lexington Test Aliquot label on a PDF"


class PrintLexingtonSampleLabelPdf(CommonsWebhookHandler):
    """
    This webhook is intended to be used on either a form view or a table view of samples, and generate the lexington
    sample labels in a pdf file for printing.

    Requirement Documentation: https://onetakeda.atlassian.net/browse/ELNMSLAB-273
    """
    rec_handler: RecordHandler

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Utils.
        label_util: LabelUtil = LabelUtil(context)

        # Setup record handler, add samples add record models.
        samples: List[SampleModel] = self.inst_man.add_existing_records_of_type(context.data_record_list, SampleModel)

        # Prompt for label details, and calculate how many blank labels there should be.
        label_details: Dict[str, Any] = label_util.prompt_for_label_details()
        num_labels = label_details.get(LabelUtil.PDF_POPUP_NUM_LABELS_FIELD)
        start_row = label_details.get(LabelUtil.PDF_POPUP_LABEL_START_ROW)
        start_column = label_details.get(LabelUtil.PDF_POPUP_LABEL_START_COLUMN)

        # Find Takeda label definition for " Lexington sample label on a PDF"
        definition: C_TakedaLabelDefinitionModel = label_util.get_takeda_label_definition(LEXINGTON_LABEL_ON_A_PDF)

        # Build our page
        page = LabelPage(context, definition, start_row, start_column)

        # Load the related records based on our label definition. Then add labels for each sample.
        page.load_related_records(samples)
        for sample in samples:
            page.add_label(RecordModelWrapperUtil.unwrap(sample), num_labels)

        # Write to client.
        pdf_bytes: bytes = page.output().getvalue()
        CallbackUtil(context).write_file("Labels.pdf", pdf_bytes)

        # All done.
        return SapioWebhookResult(True)

class PrintLexingtonLabelFromTestAliquot(CommonsWebhookHandler):

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Utils.
        label_util: LabelUtil = LabelUtil(context)

        # Setup record handler, add samples add record models.
        aliquots: List[C_TestAliquotModel] = self.inst_man.add_existing_records_of_type(context.data_record_list, C_TestAliquotModel)

        # Prompt for label details, and calculate how many blank labels there should be.
        label_details: Dict[str, Any] = label_util.prompt_for_label_details()
        num_labels = label_details.get(LabelUtil.PDF_POPUP_NUM_LABELS_FIELD)
        start_row = label_details.get(LabelUtil.PDF_POPUP_LABEL_START_ROW)
        start_column = label_details.get(LabelUtil.PDF_POPUP_LABEL_START_COLUMN)

        # Find Takeda label definition for " Lexington sample label on a PDF"
        definition: C_TakedaLabelDefinitionModel = label_util.get_takeda_label_definition(TEST_ALIQUOT_LABEL_ON_A_PDF)

        # Build our page
        page = LabelPage(context, definition, start_row, start_column)

        # Load the related records based on our label definition. Then add labels for each sample.
        page.load_related_records(aliquots)
        for sample in aliquots:
            page.add_label(RecordModelWrapperUtil.unwrap(sample), num_labels)

        # Write to client.
        pdf_bytes: bytes = page.output().getvalue()
        CallbackUtil(context).write_file("Labels.pdf", pdf_bytes)

        # All done.
        return SapioWebhookResult(True)


class PrintIntermediateLabelPDF(CommonsWebhookHandler):
    """
    This webhook will be invoked only for sample detail tables in purification and create a label pdf.
    """

    def execute(self, context: SapioWebhookContext) -> SapioWebhookResult:
        # Utils.
        label_util: LabelUtil = LabelUtil(context)

        # Setup record handler, add samples add record models.
        details: List[ELNSampleDetailModel] = self.inst_man.add_existing_records_of_type(context.data_record_list, ELNSampleDetailModel)

        # Prompt for label details, and calculate how many blank labels there should be.
        label_details: Dict[str, Any] = label_util.prompt_for_label_details()
        num_labels = label_details.get(LabelUtil.PDF_POPUP_NUM_LABELS_FIELD)
        start_row = label_details.get(LabelUtil.PDF_POPUP_LABEL_START_ROW)
        start_column = label_details.get(LabelUtil.PDF_POPUP_LABEL_START_COLUMN)

        # Find Takeda label definition for " Lexington sample label on a PDF"
        definition: C_TakedaLabelDefinitionModel = label_util.get_takeda_label_definition(INTERMEDIATE_LABEL_ON_A_PDF)

        # Build our page
        page = LabelPage(context, definition, start_row, start_column)

        # Load the related records based on our label definition. Then add labels for each sample.
        page.load_related_records(details)
        for sample in details:
            page.add_label(self.inst_man.unwrap(sample), num_labels)

        # Write to client.
        pdf_bytes: bytes = page.output().getvalue()
        CallbackUtil(context).write_file("Labels.pdf", pdf_bytes)

        # All done.
        return SapioWebhookResult(True)




