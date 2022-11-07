FROM python:3.10-alpine

WORKDIR /app

COPY poetry.lock poetry.toml pyproject.toml /app/

# Install Poetry & dependencies
RUN apk add --no-cache curl gcc libressl-dev musl-dev libffi-dev && \
    pip install -U pip setuptools && \
    pip install poetry && \
    poetry install --no-dev && \
    apk del curl gcc libressl-dev musl-dev libffi-dev

COPY . /app/

ENTRYPOINT [ "poetry", "run", "./ixpmac.py" ]