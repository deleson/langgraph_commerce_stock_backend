"""业务 Router 包。

routers 包按业务模块拆分 HTTP 入口。每个 Router 只负责路径、参数、鉴权依赖
和响应包装，复杂业务逻辑应继续下沉到 Service 层。
"""
