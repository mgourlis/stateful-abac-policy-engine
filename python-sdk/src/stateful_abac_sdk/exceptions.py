class StatefulABACError(Exception):
    """Base exception for Stateful ABAC SDK"""
    pass

class AuthenticationError(StatefulABACError):
    """Raised when authentication fails"""
    pass

class ApiError(StatefulABACError):
    """Raised when the API returns an error status"""
    def __init__(self, status_code: int, message: str, details: dict = None):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"API Error {status_code}: {message}")
