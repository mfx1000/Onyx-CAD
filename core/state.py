"""
ModelState — holds the XDE document and per-face data for a loaded STEP file.

ModelStateManager — per-user-session state management with LRU eviction.
The global `model` variable is kept for backward compatibility with loader.py
and exporter.py (which import it by name).  The manager swaps what `model`
points to via the context manager protocol.
"""
import threading
from collections import OrderedDict

from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool


class ModelState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.doc = None
        self.xcaf_app = None
        self.shape_tool = None
        self.color_tool = None
        self.face_shapes = []
        self.face_labels = []
        self.face_hashes = []       # list[str] — geometry fingerprint per face
        self.face_raws = []         # list[dict] — raw fingerprint values per face
        self.face_meta = {}         # dict[int, dict] — per-face metadata
        self.faces_cache = None     # cached tessellated mesh data (vertices/normals/indices)
        self.original_filename = ""
        self.model_uuid = None      # unique identifier for current model


# ── Global model instance ────────────────────────────────────────────────────
# This is kept for backward compatibility: loader.py and exporter.py both
# do ``from core.state import model`` and read/write its attributes directly.
# The ModelStateManager swaps what this object's attributes point to via
# the context-manager protocol, so the *reference identity* stays the same
# but the underlying data changes per (user_id, model_id) pair.
model = ModelState()


class _ActiveModelProxy:
    """
    Context manager that temporarily swaps the global ``model`` attributes
    to match a specific per-user ModelState, then restores them.

    Usage:
        with manager.activate(user_id, model_id) as state:
            # global ``model`` now has state's attributes
            load_step_xcaf(path)   # mutates ``model``, i.e. ``state``
    """

    def __init__(self, manager: "ModelStateManager", key: tuple):
        self._manager = manager
        self._key = key

    def __enter__(self) -> ModelState:
        self._manager._lock.acquire()
        state = self._manager._states.get(self._key)
        if state is None:
            state = ModelState()
            self._manager._states[self._key] = state
        # Copy state attributes onto the global model object
        _copy_state(src=state, dst=model)
        return state

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Copy current global model attributes back into the stored state
        state = self._manager._states.get(self._key)
        if state is not None:
            _copy_state(src=model, dst=state)
        self._manager._lock.release()
        return False


def _copy_state(src: ModelState, dst: ModelState):
    """Copy all fields from src to dst (shallow copy of lists/dicts)."""
    dst.doc = src.doc
    dst.xcaf_app = src.xcaf_app
    dst.shape_tool = src.shape_tool
    dst.color_tool = src.color_tool
    dst.face_shapes = list(src.face_shapes)
    dst.face_labels = list(src.face_labels)
    dst.face_hashes = list(src.face_hashes)
    dst.face_raws = list(src.face_raws)
    dst.face_meta = dict(src.face_meta)
    dst.original_filename = src.original_filename
    dst.model_uuid = src.model_uuid


class ModelStateManager:
    """
    Manages per-(user_id, model_id) ModelState instances.
    Uses an OrderedDict for LRU eviction when the pool exceeds max_size.
    """

    def __init__(self, max_size: int = 50):
        self._states: OrderedDict[tuple, ModelState] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    # ── Context manager (primary API) ────────────────────────────────────

    def activate(self, user_id: str, model_id: str) -> _ActiveModelProxy:
        """
        Return a context manager that swaps the global ``model`` to the
        state for (user_id, model_id).  Creates the state if it does not
        exist yet.

        Usage:
            with manager.activate(user_id, model_id) as state:
                load_step_xcaf(path)
        """
        key = (user_id, model_id)
        return _ActiveModelProxy(self, key)

    # ── Direct access ────────────────────────────────────────────────────

    def get_state(self, user_id: str, model_id: str) -> ModelState:
        """Return the state for (user_id, model_id), creating if absent."""
        key = (user_id, model_id)
        with self._lock:
            if key not in self._states:
                self._evict_if_needed()
                self._states[key] = ModelState()
            else:
                self._states.move_to_end(key)
            return self._states[key]

    def clear_state(self, user_id: str, model_id: str):
        """Remove the state for (user_id, model_id)."""
        key = (user_id, model_id)
        with self._lock:
            self._states.pop(key, None)

    # ── LRU eviction ─────────────────────────────────────────────────────

    def _evict_if_needed(self):
        """Evict the oldest entry if the pool is at capacity."""
        while len(self._states) >= self._max_size:
            self._states.popitem(last=False)


# ── Module-level manager instance ────────────────────────────────────────────
manager = ModelStateManager(max_size=50)
