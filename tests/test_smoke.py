from app.main import app


def test_app_can_be_imported() -> None:
    assert app is not None


def test_app_title_exists() -> None:
    assert app.title