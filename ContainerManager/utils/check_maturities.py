

def check_maturities(maturity: str) -> None:
    """
    Makes sure the maturity is valid, including case-sensitivity.
    Factored to it's own method because of https://github.com/Cameronsplaze/AWS-ContainerManager/pull/180
    """
    supported_maturities = ["Devel", "Prod"]
    assert maturity in supported_maturities, f"ERROR: Unknown maturity ({maturity}). Must be in {supported_maturities}"
