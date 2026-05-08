FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    git curl wget nano nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /app/workspace

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "agent.py"]
