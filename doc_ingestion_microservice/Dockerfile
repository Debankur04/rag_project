FROM python:3.12-slim
WORKDIR /app
COPY requirements_pip.txt ./
RUN pip install --no-cache-dir -r requirements_pip.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
