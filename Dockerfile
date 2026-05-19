FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    wget \
    tar \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY config/requirements/ /app/config/requirements/
RUN pip install --no-cache-dir -r config/requirements/base.txt

COPY . /app/

EXPOSE 8000