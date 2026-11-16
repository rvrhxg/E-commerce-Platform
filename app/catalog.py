"""Keyset catalog traversal with a high-water ID and bound query filters."""
import base64
import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Cursor:
    after: int
    ceiling: int
    scope: str

    def encode(self) -> str:
        raw = json.dumps([self.after, self.ceiling, self.scope], separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, token: str, scope: str) -> "Cursor":
        try:
            values = json.loads(base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True))
            if not isinstance(values, list) or len(values) != 3:
                raise ValueError
            after, ceiling, saved_scope = values
            if type(after) is not int or type(ceiling) is not int or not 0 <= after <= ceiling or saved_scope != scope:
                raise ValueError
            return cls(after, ceiling, scope)
        except (ValueError, TypeError, UnicodeDecodeError) as error:
            raise ValueError("Invalid cursor or changed filters") from error


def scope_for(filters: tuple[object, ...]) -> str:
    return hashlib.sha256(json.dumps(filters, ensure_ascii=False).encode()).hexdigest()[:24]
