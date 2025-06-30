from typing import List, Dict, Any

from sapiopycommons.callbacks.callback_util import CallbackUtil
from sapiopycommons.general.aliases import UserIdentifier
from sapiopycommons.recordmodel.record_handler import RecordHandler
from sapiopylib.rest.User import SapioUser
from sapiopylib.rest.pojo.datatype.FieldDefinition import AbstractVeloxFieldDefinition
from sapiopylib.rest.utils.DataTypeCacheManager import DataTypeCacheManager
from sapiopylib.rest.utils.recordmodel.RecordModelManager import RecordModelRelationshipManager
from sapiopylib.rest.utils.recordmodel.RecordModelUtil import RecordModelUtil
from sapiopylib.rest.utils.recordmodel.RecordModelWrapper import RecordModelWrapperUtil
from sapiopylib.rest.utils.recordmodel.RelationshipPath import RelationshipPath
from sapiopylib.rest.utils.recordmodel.properties import Ancestors

from sapio.model.data_type_models import SampleModel, C_TestAliquotModel, StudyModel


class TestAliquotCreator:
    """
    Contains the methods necessary for the basic test aliquot creation process.
    TODO: Perhaps make this a more advanced manager.
    """

    user: SapioUser
    """ The user object for instantiating any objects interacting with the API. """
    rec_handler: RecordHandler
    """ The record handler for dealing with records in a simpler fashion. """
    rel_man: RecordModelRelationshipManager
    """ For loading relationships. """

    def __init__(self, user: UserIdentifier):
        self.user = user if isinstance(user, SapioUser) else user.user
        self.rec_handler = RecordHandler(user)
        self.rel_man = self.rec_handler.rel_man

    def prompt_user_with_aliquot_details(self,
                                         highest_aliquot_numbers_per_sample: list[int],
                                         number_of_aliquots_to_create: int,
                                         samples: list[SampleModel],
                                         override_fields_per_sample: list[Dict[str, Any]] = None,
                                         default_row_values: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Prompts the user with a table of aliquot detail data, and returns the input from the user.

        :param highest_aliquot_number: The current highest aliquot number. All of the aliquot numbers in this dialog
            should be higher than this value.
        :param number_of_aliquots_to_create: The number of aliquots to create, which will match the number of rows in
            the table.
        :param sample: The sample to base the data for these Test Aliquot records on.
        :param default_row_values: A dictionary with default values to be used for each row in the table. These values
            will be overwritten by the user's input.
        :param override_fields: A dictionary with values to be used for each row in the table. These values will
            overwrite the default values and the user's input.
        :returns: The list of field maps to create the Test Aliquot records with.
        """

        # Compile default values for each Test aliquot to create.
        default_values: List[Dict[str, Any]] = list()

        index = -1

        for sample in samples:

            index += 1
            override_fields = None
            highest_aliquot_number = highest_aliquot_numbers_per_sample[index]

            if override_fields_per_sample is not None:
                override_fields = override_fields_per_sample[index]

            # Get the Product and Study Name from the samples Study Ancestor.
            self.rel_man.load_path_of_type([sample], RelationshipPath().ancestor_type(StudyModel))
            studies: List[StudyModel] = sample.get(Ancestors.of_type(StudyModel))
            product = ""
            study_name = ""
            if len(studies) > 0:
                # Get all the values, and then set the product and study name to be a sorted comma delimited list.
                all_products = RecordModelUtil.get_value_list(RecordModelWrapperUtil.unwrap_list(studies), StudyModel.C_PRODUCT__FIELD_NAME.field_name)
                all_study_names = RecordModelUtil.get_value_list(RecordModelWrapperUtil.unwrap_list(studies), StudyModel.STUDYNAME__FIELD_NAME.field_name)
                all_products.sort()
                all_study_names.sort()
                product = ", ".join(all_products)
                study_name = ", ".join(all_study_names)

            hard_coded_values_per_sample: Dict[int, Dict[str, Any]] = dict()

            for i in range(number_of_aliquots_to_create):
                aliquot_number = highest_aliquot_number + (i + 1)
                default_row = self.get_table_default_row(sample, product, study_name, aliquot_number)
                hard_coded_values = self.get_hard_coded_values(sample, product, study_name, aliquot_number)

                # Add an ability for overriding defaults without full overwrite
                if default_row_values is not None:
                    default_row.update(default_row_values)

                # Add in ability for overriding fields when invoking this.
                if override_fields is not None:
                    default_row.update(override_fields)
                    hard_coded_values.update(override_fields)
                default_values.append(default_row)
                hard_coded_values_per_sample[aliquot_number] = hard_coded_values

        # Compile none system fields for display. Try to respect key field order as well.
        fields: Dict[str, AbstractVeloxFieldDefinition] = DataTypeCacheManager(self.user).get_fields_for_type(
            C_TestAliquotModel.DATA_TYPE_NAME)
        table_fields: List[AbstractVeloxFieldDefinition] = list()
        for field in fields.values():
            if not field.system_field:
                if field.data_field_name == C_TestAliquotModel.C_ASSAY__FIELD_NAME.field_name:
                    field.editable = True
                if field.key_field:
                    table_fields.append(field)
        table_fields.sort(key=lambda x: x.key_field_order)

        # Use same list of values when iterating if an error is present so that user's values are not reset
        result_values: List[Dict[str, Any]] = default_values

        error_msg = None
        while True:

            result_values = CallbackUtil(self.user).table_dialog("Create Test Aliquots",
                                                                                       error_msg,
                                                                                       table_fields,
                                                                                       result_values,
                                                                                       data_type=C_TestAliquotModel.DATA_TYPE_NAME)
            error_msg = None
            for row in result_values:
                designation = row.get(C_TestAliquotModel.C_DESIGNATION__FIELD_NAME.field_name, "")
                assay = row.get(C_TestAliquotModel.C_ASSAY__FIELD_NAME.field_name, None)
                if designation != "Storage" and not assay:
                    error_msg = (
                        "<p style=\"color: red;\">ERROR: An Assay is required when a Designation is anything other than 'Storage'!</p>"
                    )
                    break

            if not error_msg:
                break

        return result_values

    def get_highest_aliquot_number(self, sample: SampleModel) -> int:
        """
        Iterate over the samples Test aliquot children, and grab the highest value from "highest aliquot number".

        :param sample: The SampleModel to get the highest aliquot number for.
        :returns: The highest aliquot number among the samples Test Aliquot children, or 0 if none are found.
        """
        self.rel_man.load_children_of_type([sample], C_TestAliquotModel)
        test_aliquots: List[C_TestAliquotModel] = sample.get_children_of_type(C_TestAliquotModel)
        highest_aliquot_number: int | None = None
        for test_aliquot in test_aliquots:
            if highest_aliquot_number is None or highest_aliquot_number < test_aliquot.get_C_AliquotNumber_field():
                highest_aliquot_number = test_aliquot.get_C_AliquotNumber_field()

        if highest_aliquot_number is None:
            highest_aliquot_number = 0
        return highest_aliquot_number

    def prompt_for_number_of_aliquots_to_create(self):
        """
        Display an integer dialog promting the user for how many Test Aliquots to create.

        :returns: The number of aliquots entered by the user
        """
        number_of_aliquots_to_create = CallbackUtil(self.user).integer_input_dialog("Create Test Aliquots",
                                                                                  "How many Test Aliquots would you like to create?",
                                                                                  "Desired Aliquot Count",
                                                                                  1,
                                                                                  1)
        return number_of_aliquots_to_create

    def get_table_default_row(self, sample, product, study_name, aliquot_number):
        row_values = dict()
        row_values[C_TestAliquotModel.C_SAMPLEID__FIELD_NAME.field_name] = sample.get_SampleId_field()
        row_values[C_TestAliquotModel.C_OTHERSAMPLEID__FIELD_NAME.field_name] = sample.get_OtherSampleId_field()
        row_values[
            C_TestAliquotModel.C_TESTALIQUOTSAMPLEID__FIELD_NAME.field_name] = sample.get_SampleId_field() + "-T" + str(
            aliquot_number)
        row_values[C_TestAliquotModel.C_ALIQUOTNUMBER__FIELD_NAME.field_name] = aliquot_number
        row_values[C_TestAliquotModel.C_SAMPLETYPE__FIELD_NAME.field_name] = sample.get_ExemplarSampleType_field()
        row_values[C_TestAliquotModel.C_DESIGNATION__FIELD_NAME.field_name] = "Storage"
        row_values[C_TestAliquotModel.C_STATUS__FIELD_NAME.field_name] = "Ready"
        row_values[C_TestAliquotModel.C_CONCENTRATIONUNITS__FIELD_NAME.field_name] = "mg/mL"
        row_values[C_TestAliquotModel.C_VOLUMEUNITS__FIELD_NAME.field_name] = "µL"
        row_values[C_TestAliquotModel.C_PRODUCT__FIELD_NAME.field_name] = product
        row_values[C_TestAliquotModel.C_STUDYNAME__FIELD_NAME.field_name] = study_name
        return row_values

    def get_hard_coded_values(self, sample, product, study_name, aliquot_number):
        """
        These values will be set back onto the matching result from the table dialog, whether they are displayed or not.
        """
        hard_coded_values = dict()
        hard_coded_values[C_TestAliquotModel.C_SAMPLEID__FIELD_NAME.field_name] = sample.get_SampleId_field()
        hard_coded_values[C_TestAliquotModel.C_TESTALIQUOTSAMPLEID__FIELD_NAME.field_name] = sample.get_SampleId_field() + "-T" + str(aliquot_number)
        hard_coded_values[C_TestAliquotModel.C_ALIQUOTNUMBER__FIELD_NAME.field_name] = aliquot_number
        hard_coded_values[C_TestAliquotModel.C_STUDYNAME__FIELD_NAME.field_name] = study_name
        hard_coded_values[C_TestAliquotModel.C_PRODUCT__FIELD_NAME.field_name] = product
        return hard_coded_values