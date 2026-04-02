"""
STEP file exporter — writes XDE document with colors + metadata injection.

Now accepts a ModelState instance so it works with per-user session state
instead of relying on a module-level global.
"""

import os
import io
import uuid

from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

from core.state import ModelState
from core.metadata import inject_meta_into_step


def export_step_xcaf(model_state: ModelState,
                     upload_folder: str) -> tuple[str, str, io.BytesIO]:
    """
    Export the current model to a STEP file with metadata injected.
    Returns (download_filename, mimetype, file_bytes_io).
    """
    if model_state.doc is None:
        raise RuntimeError("No model loaded")

    export_path = os.path.join(
        upload_folder, f"{uuid.uuid4().hex}_export.step"
    )

    try:
        writer = STEPCAFControl_Writer()
        writer.SetColorMode(True)
        writer.SetNameMode(True)
        writer.SetLayerMode(True)

        if not writer.Transfer(model_state.doc, STEPControl_AsIs):
            raise RuntimeError("Writer transfer failed")

        status = writer.Write(export_path)
        if status != IFSelect_RetDone:
            raise RuntimeError(f"Write failed (status {status})")

        with open(export_path, "rb") as ef:
            file_bytes = ef.read()

        # ── Inject metadata into the STEP file ──────────────────────────
        if model_state.face_meta:
            # Legacy index-based metadata (for backward compat)
            meta_payload = {"face_meta": {str(k): v for k, v in model_state.face_meta.items()}}

            # Robust hash-based metadata (resilient to face reordering)
            meta_by_hash = {}
            for face_id, meta in model_state.face_meta.items():
                if face_id < len(model_state.face_hashes):
                    fh = model_state.face_hashes[face_id]
                    if fh and fh != "unknown":
                        meta_by_hash[fh] = meta

            if meta_by_hash:
                meta_payload["face_meta_by_hash"] = meta_by_hash

            file_bytes = inject_meta_into_step(file_bytes, meta_payload)

        return (
            f"{model_state.original_filename}_colored.step",
            "application/octet-stream",
            io.BytesIO(file_bytes),
        )

    finally:
        if os.path.exists(export_path):
            os.remove(export_path)
