class ReviewStatuses:
    """
    A class storing str constants for the "Review Statuses" pick list.
    """
    READY_FOR_REVIEW: str = "Ready for Review"
    IN_REVIEW: str = "In Review"
    APPROVED: str = "Approved"
    REJECTED: str = "Rejected"
    OPEN: str = "Open"


class TestAliquotStatuses:
    """
    A class storing str constants for storing test aliquot status values.
    """
    READY: str = "Ready"
    IN_PROCESS: str = "In Process"
    PASS: str = "Pass"
    FAIL: str = "Fail"


class PassFailValues:
    """
    A class storing str constants for storing pass/fail values.
    """
    PASS: str = "Pass"
    FAIL: str = "Fail"