def test_pydantic_major_version_is_v2():
    import pydantic

    assert int(pydantic.__version__.split(".", 1)[0]) == 2
