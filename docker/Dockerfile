FROM python:3.9-slim

WORKDIR /app

COPY . /app/

RUN pip install --upgrade pip \
    --no-cache-dir \
    kubernetes==26.1.0 \
    requests \
    typing_extensions

ENV PYTHONUNBUFFERED=1

CMD ["python", "dynamicollector.py"]