from flask import jsonify


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def error_response(status, code, message):
    return jsonify(error=dict(code=code, message=message)), status
