"""后端应用入口烟雾测试。

只验证 FastAPI app 能被导入、基础元信息存在。
这是最轻量的回归检查，适合在大改动后先跑一遍。
"""

from app.main import app


def test_app_can_be_imported() -> None:
    assert app is not None


def test_app_title_exists() -> None:
    assert app.title
