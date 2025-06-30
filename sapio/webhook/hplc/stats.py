class LinRegressData:
    """
    A wrapper for the LinregressResult instance. The actual result from scipy doesn't seem to have typing that works
    well with the IDE, so this wrapper makes it clear what attributes are available and makes it easier to get them.

    Attributes:
        - result: The LinregressResult instance to be wrapped.
    """

    def __init__(self, result):
        self._result = result

    def get_slope(self):
        """Returns the slope of the regression line."""
        return self._result.slope

    def get_intercept(self):
        """Returns the intercept of the regression line."""
        return self._result.intercept

    def get_rvalue(self):
        """Returns the Pearson correlation coefficient."""
        return self._result.rvalue

    def get_r_squared(self):
        """Returns the coefficient of determination"""
        return self._result.rvalue * self._result.rvalue

    def get_pvalue(self):
        """Returns the p-value for the hypothesis test."""
        return self._result.pvalue

    def get_stderr(self):
        """Returns the standard error of the estimated slope."""
        return self._result.stderr

    def get_intercept_stderr(self):
        """Returns the standard error of the estimated intercept."""
        return self._result.intercept_stderr
