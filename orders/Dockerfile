FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py otel_setup.py orders_pb2.py orders_pb2_grpc.py ./

EXPOSE 50051
ENV GRPC_PORT=50051

CMD ["python", "main.py"]
