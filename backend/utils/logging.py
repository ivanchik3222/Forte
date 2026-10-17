import logging
import re


class RedactMediaSignature(logging.Filter):
    """Werkzeug's local access log must not expose signed media links."""
    def filter(self, record):
        record.msg = re.sub(r'([?&]token=)[^\s&"\']+', r'\1[redacted]', record.getMessage())
        record.args = ()
        return True
