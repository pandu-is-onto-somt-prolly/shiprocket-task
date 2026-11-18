"""Per-conversation speech guards; business records remain in Store."""
from dataclasses import dataclass, field
import time
from .core import affirmative


@dataclass
class SpeechGuard:
    latest_user_text: str = ""
    readback_revision: int | None = None
    pending_readback_revision: int | None = None
    speaking: bool = False
    has_spoken: bool = False
    interrupted_readback: bool = False
    readback_kind: str | None = None
    callback_preference: str | None = None
    silence_count: int = 0
    repair_count: int = 0
    total_turns: int = 0
    awaiting_response: bool = False
    progress: float = field(default_factory=time.monotonic)

    def arm_readback(self, revision: int, kind: str):
        self.readback_revision = None
        self.pending_readback_revision = revision
        self.interrupted_readback = False
        self.readback_kind = kind
        self.latest_user_text = ""

    def user_started(self):
        if self.pending_readback_revision is not None:
            self.interrupted_readback = True
            self.readback_revision = None

    def bot_started(self):
        self.speaking = True
        self.has_spoken = True
        self.awaiting_response = False
        self.progress = time.monotonic()

    def bot_stopped(self):
        was_speaking = self.speaking
        self.speaking = False
        if self.pending_readback_revision is not None:
            if was_speaking and not self.interrupted_readback:
                self.readback_revision = self.pending_readback_revision
            self.pending_readback_revision = None
        self.progress = time.monotonic()

    def user_text(self, text: str):
        # Also reject early confirmations if a VAD start event was missed.
        if self.pending_readback_revision is not None:
            self.interrupted_readback = True
            self.readback_revision = None
        self.latest_user_text = text
        self.silence_count = 0
        self.total_turns += 1
        self.awaiting_response = True
        self.progress = time.monotonic()

    def can_confirm(self, revision: int, kind: str) -> bool:
        return not self.speaking and self.readback_kind == kind and self.readback_revision == revision and affirmative(self.latest_user_text)

    def changed(self):
        self.readback_revision = self.pending_readback_revision = None
        self.readback_kind = None

    def repair(self) -> bool:
        self.repair_count += 1
        return self.repair_count <= 2

    def idle(self) -> str:
        self.silence_count += 1
        return "remind" if self.silence_count <= 2 else "end"
