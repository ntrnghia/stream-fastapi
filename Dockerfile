FROM python:slim

WORKDIR /app

RUN python -m pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

RUN sed -i 's/\(deb\(-src\)\? .*\) main/\1 main contrib non-free/g' /etc/apt/sources.list
RUN apt update && apt-get install unrar

CMD uvicorn app:app --host 0.0.0.0 --port 8000 --log-level debug
