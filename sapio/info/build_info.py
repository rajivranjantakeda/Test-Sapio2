class BuildInfo:
    BUILD_NUMBER = "2025_03_14"
    BRANCH = "rc/8.5"

    @staticmethod
    def print_info():
        return "(" + BuildInfo.BRANCH + ") " + BuildInfo.BUILD_NUMBER
