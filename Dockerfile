FROM python:3.11-alpine

WORKDIR /app

COPY . .

RUN apk add --no-cache \
      libxml2 libxslt libffi openssl zlib libjpeg-turbo postgresql-libs

RUN apk add --no-cache --virtual .build-deps \
      build-base libxml2-dev libxslt-dev libffi-dev openssl-dev zlib-dev postgresql-dev

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir .[dev]
RUN apk del .build-deps

CMD ["python", "-m", "uvicorn", "dba_agent.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
