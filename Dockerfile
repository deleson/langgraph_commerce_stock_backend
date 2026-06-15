FROM python:3.11-slim

# 生产镜像基础环境：
# 关闭 pyc 写入、开启实时日志输出，并让 uv / pip 默认使用国内镜像以降低服务器构建超时概率。
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV UV_DEFAULT_INDEX=https://mirrors.tencent.com/pypi/simple
ENV PIP_INDEX_URL=https://mirrors.tencent.com/pypi/simple

WORKDIR /app

# 安装编译 Python 依赖和 psycopg 所需的系统包。
# 这里没有复制 .env.production，真实配置会在 docker compose 运行时通过 env_file 注入。
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org/debian|https://mirrors.tencent.com/debian|g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's|http://deb.debian.org/debian-security|https://mirrors.tencent.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        gcc \
        build-essential \
        libpq-dev; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# 先复制依赖文件，再执行 uv sync，可以利用 Docker 构建缓存。
# 只有 pyproject.toml 或 uv.lock 变化时才会重新安装依赖。
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

# 生产镜像只包含运行所需的迁移文件和 app 代码。
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# 8000 只暴露给 Docker 内部网络；公网入口由 nginx 的 80 端口负责。
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
