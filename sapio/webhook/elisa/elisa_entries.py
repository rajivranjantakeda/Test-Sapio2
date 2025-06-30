class SampleDilutionTargets:
    """ Class to store field names for the Sample Dilution Targets entry in ELISA. """
    TARGET_DILUTION_FACTOR: str = "TargetDilution"
    DILUTION_NUMBER: str = "Dilution"


class SampleDilution:
    DILUTION: str = "Dilution"
    SAMPLE_VOLUME: str = "SampleVolumeuL"
    DILUENT_VOLUME: str = "DiluentVolumeuL"
    TOTAL_VOLUME: str = "TotalVolumeuL"
    FINAL_DILUTION_FACTOR: str = "FinalDilutionFactor"


class SampleData:
    CV = "CV"
    DILUTION = "Dilution"
    DILUTION_FACTOR = "DilutionFactor"
    I2S = "I2SngmL"


class SampleDataAverages:
    AVG_I2S: str = "AvgI2SngmL"
    INTER_DIL_CV: str = "InterDilCV"
