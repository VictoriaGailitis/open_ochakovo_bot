class APIError(Exception):
    def __init__(self, status, message, code='invalid_request', details=None):
        self.status, self.message, self.code, self.details = status, message, code, details
