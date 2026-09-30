from src.openai_model import OpenAIChatModel


def test_api_key_is_masked_in_model_representation_and_serialization():
    secret = "test-secret-api-key"
    model = OpenAIChatModel(
        model="freecoding",
        api_key=secret,
        base_url="http://localhost:20128/v1",
    )

    assert secret not in repr(model)
    assert secret not in str(model.model_dump())
    assert model.api_key.get_secret_value() == secret
