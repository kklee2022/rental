from contextvars import ContextVar

_request_id = ContextVar("request_id", default=None)


def get_request_id():
    return _request_id.get()


def set_request_id(value):
    return _request_id.set(value)


def reset_request_id(token):
    _request_id.reset(token)
