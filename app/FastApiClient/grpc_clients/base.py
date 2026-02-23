import grpc
from typing import Optional

class BaseGrpcClient:
    """Базовый класс для gRPC клиентов с поддержкой таймаута и обработки ошибок."""
    def __init__(self, server_address: str):
        self.channel = grpc.insecure_channel(server_address)
        # Можно добавить интерцепторы для логирования/метрик

    def _handle_rpc_error(self, e: grpc.RpcError):
        # Преобразуем gRPC ошибки в понятные исключения
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise ValueError(e.details())  # можно создать свой тип
        elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise PermissionError(e.details())
        else:
            raise Exception(f"gRPC error: {e.code()} - {e.details()}")