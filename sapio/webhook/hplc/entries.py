class HPLCRawDataFields:
    """
    A class for statically referencing the data field names used in the HPLC Raw Data entries.
    """
    SAMPLE_NAME: str = "OtherSampleId"
    NAME: str = "Name"
    DATE_ACQUIRED: str = "DateAcquired"
    AREA: str = "Area"
    USP_PLATE_COUNT: str = "USPPlateCount"
    USP_TAILING: str = "USPTailing"
    RETENTION_TIME: str = "RetentionTime"


class SlopeInterceptFields:
    """
    A class for statically referencing the data field names used in the Slope / Intercept entry of HPLC.
    """
    SLOPE: str = "Slope"
    R2: str = "R2"
    SPEC: str = "Spec"
    INTERCEPT: str = "Intercept"


class ReferenceStandardDataFields:
    """
    A class for statically referencing the data field names used in the HPLC entry for Reference Standard Data.
    """
    SAMPLE_NAME: str = "SampleName"
    MAIN_PEAK_RETENTION_TIME: str = "MainPeakRetentionTimemin"
    MAIN_PEAK_AREA: str = "MainPeakArea"
    CONCENTRATION: str = "Concentrationug"
    Y_MINUS_B: str = "yb"
    M: str = "m"
    PERCENT_RECOVERY: str = "Recovery"


class AssayControlDataFields:
    """
    A class for statically referencing the data field names used in the HPLC entry for Assay Control Data.
    """
    SAMPLE_NAME: str = "SampleName"
    AREA: str = "Area"
    AVERAGE_PEAK_AREA: str = "AveragePeakArea"
    USP_PLATE_COUNT: str = "USPPlateCount"
    USP_TAILING: str = "USPTailing"
    RETENTION_TIME: str = "RetentionTime"
    INJECTION_VOLUME: str = "InjectionVolumeuL"
    CONCENTRATION: str = "ConcentrationmgmL"
    DIFFERENCE: str = "Difference"
    USP_PLATE_COUNT_SPEC: str = "USPPlateCountSpec"
    USP_TAILING_SPEC: str = "USPTailingSpec"
    RETENTION_TIME_SPEC: str = "RetentionTimeSpec"
    CONCENTRATION_SPEC: str = "ConcentrationSpec"
    DIFFERENCE_SPEC: str = "DifferenceSpec"
    AVERAGE_CONCENTRATION: str = "AverageConcentrationmgmL"


class SampleDataFields:
    """
    A class for statically referencing the data field names used in the HPLC entry for Sample Result Data.
    """
    DILUTION_FACTOR: str = "DilutionFactor"
    ESTIMATED_CONCENTRATIONS: str = "EstimatedConcentration_mgmL"
    INJECTION_VOLUME: str = "InjectionVolume_mL"
    INTERCEPT: str = "Intercept"
    PEAK_AREA: str = "PeakArea"
    SLOPE: str = "Slope"


class SampleDilutionFields:
    """
    A class for statically referencing the data field names used in the HPLC entry for Sample DilutionData
    """
    SAMPLE_ID: str = "SampleId"
    SAMPLE_NAME: str = "OtherSampleId"
    DILUTION_FACTOR: str = "DilutionFactor"
    ESTIMATED_CONCENTRATION: str = "SampleConcentration_mgmL"
    INJECTION_VOLUME: str = "InjectionVolume_mL"
    TARGET_CONCENTRATION: str = "TargetConcentration_mgmL"
    TOTAL_VOLUME: str = "TotalVolume_mL"
    VOLUME_OF_MPA: str = "MpaVolume_uL"
    SOURCE_VOLUME: str = "SampleVolume_mL"