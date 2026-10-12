"""Package import smoke test."""


def test_agentos_can_be_imported() -> None:
    import agentos

    assert agentos.__version__ == "0.1.0"

