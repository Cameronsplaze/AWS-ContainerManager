from enum import Enum

class Maturity(Enum):
    """
    Makes sure the maturity is valid, including case-sensitivity.
    Factored to it's own method because of https://github.com/Cameronsplaze/AWS-ContainerManager/pull/180
    """
    DEVEL = "Devel"
    PROD = "Prod"
