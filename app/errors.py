class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class WeightError(AppError):
    pass


class KeitaroError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status=502)
