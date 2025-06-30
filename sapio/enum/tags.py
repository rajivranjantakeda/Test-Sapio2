class ExperimentEntryTags:
    """" A class to store string constants for custom experiment entry tags. """

    EXPERIMENT_OVERVIEW: str = "TAKEDA EXPERIMENT OVERVIEW"
    """ The tag for the experiment overview entry, particularly used in the MarkReadyForReview webhook. """

    ASSAY_DETAILS: str = "ASSAY DETAILS"
    """ The tag used to indicate which entry contains the assay details. Particularly used for the ELISA/HPLC 
    workflows. """

    ASSAY_RESULTS: str = "TAKEDA ASSAY RESULTS"
    """ This tag will be used to indicate which entry contains the assay results. Particularly used for the ELISA/HPLC
    workflows. """

    TEST_ALIQUOTS: str = "TAKEDA TEST ALIQUOTS"
    """ This tag will be used to indicate which entry test aliquots should be added to. Currently only used in the 
    Purification workflow. """

    PHASE_STEP: str = "TAKEDA PHASE / STEP"
    """ This tag is set at the time when the building block is added to the experiment. This value depicts a phase/step
    that the user selected. """

    CREATE_SAMPLE_ALIQUOT_ENTRY: str = "SET UP ALIQUOTS"
    """ This is an out-of-box tag that is used to denote that on submission of the experiment entry, a sample aliquot 
    will be created. """

    OUTPUT_SAMPLE_TYPE_FOR_ALIQUOT: str = "SET OUTPUT SAMPLE TYPE"
    """ This is an out-of-box tag that specifies what the resulting sample type should be when the aliquot is created. """

    CONSUMABLE_ENTRY: str = "TAKEDA CONSUMABLE ENTRY"
    """ This tag identifies an entry that is used for tracking consumable usages. """

    SET_SAMPLE_TYPE_ON_SAMPLE_DETAIL: str = "TAKEDA SET SAMPLE TYPE"
    """ This tag indicates that a sample type should be set on sample detail records to either what's set on this tag 
    or most recent sample type """

    SET_CUSTOM_FIELD_VALUE: str = "TAKEDA SET CUSTOM FIELD"
    """ This tag allows definition of how to set a field when adding a building block. For example, if we need to set
    field PassagingToVesselType to value Bioreactor, then use a tag value of: PassagingToVesselType=Bioreactor;"""

    SOURCE_BUILDING_BLOCK: str = "TAKEDA SOURCE BUILDING BLOCK"
    """ This tag is used to indicate the source protocol template for a given entry. """

    PURIFICATION_PROTEIN_CAPTURE_FOR_YIELDS = "TAKEDA PURIFICATION PROTEIN CAPTURE FOR YIELDS STEP"
    """ This tag points to an entry that contains a TotalProtein field that is used in the Yields summary step. """

    NEW_SAMPLE_FIELD_VALUES: str = "NEW SAMPLE FIELD VALUES"
    """ This tag is used to specify the values that should be set on the new samples created in the experiment. "
    In particular, this is used in the AddSamplesButton. The value is expected to be formatted as a comma delimited list
    of assignments (e.g. "SampleType=Cell,CellLine=293T"). """


class ProtocolTemplateTags:
    """
    A class to store string constants for custom protocol template tags.
    """

    BUILDING_BLOCK: str = "TAKEDA BUILDING BLOCK: "
    """ This tag is used to indicate that the protocol template is a building block. After the colon, the name of the 
    template where this building block can be applied is expected. If the subsequent value is 'Universal', then the 
    block should always appear in the selection."""

    BUILDING_BLOCK_SAMPLE_LIMIT: str = "TAKEDA BUILDING BLOCK RESTRICT TO ONE SAMPLE"
    """ Within the building block grabber, this tag will cause the grabber to cancel if more than one sample is found 
    in the most recent samples table (to be used as a source). """

    TITLE_PROMPT_TAG_REGEX = r"TAKEDA BUILDING BLOCK PROMPT FOR ENTRY NAME PREFIX \[PROMPT TITLE: ([^\]]+)] \[PROMPT MESSAGE: ([^\]]+)]"
    """ A regex tag for the building block grabber. This indicates that the title will be prompted for using a free text
    input dialog. """

    TITLE_PICKLIST_PROMPT_TAG_REGEX = r"TAKEDA BUILDING BLOCK PHASE \[PROMPT PICKLIST: ([^\]]+)] \[MESSAGE: ([^\]]+)]"
    """ A regex tag for the building block grabber. This indicates that the title will be prompted for using a picklist
    dialog. """

    TITLE_SPECIFIC_TAG_REGEX = r"TAKEDA BUILDING BLOCK PHASE \[NAME: ([^\]]+)]"
    """ A regex tag for the building block grabber. This indicates that the title will be hardcoded using this regex 
    value as the title. """


class DataFieldTags:
    """
    A class to store string constants and regex's for custom data field tags.
    """
    DYNAMIC_SELECTION_LIST_TAG = r"<!--\s*TAKEDA\s*DYNAMIC\s*SELECTION\s*:\s*DATA\s*TYPE\s*\[(.*?)\]\s*FILTER\s*BY\s*FIELD\s*\[(.*?)\]\s*-->"
    """ This field tag is used by the DynamicSelection webhook to determine which data type to use for key-key value 
    pairs, and what field on the current record the key value will be pulled from. """


class DataTypeTags:
    """
    A class to store string constants and regex's for custom data type tags.
    """
    WHEN_NEW_ADD_TO = r"<!--\s*WHEN\s*NEW\s*ADD\s*TO:\s*(\w+)\s*-->"
    """ This tag is used by the AddParentOnSave webhook to determine which parent type to add the new record to. The 
    parent type is expected to only have one accessible record, and the webhook will add the new record to the first
    available record. """


class TemplateDescriptionTags:
    """
    A class to store string constants and regex's for custom template description tags.
    """
    TEMPLATE_DESIGNATION = r"TAKEDA TEST ALIQUOT DESIGNATION: ([\w\s/]+)"
    """ This tag is used to determine the designation of a template. """