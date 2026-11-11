"""Keep the hook tests away from the real event log."""

import atexit
import os
import shutil
import tempfile

_STATE = tempfile.mkdtemp(prefix="pkit-state-")
atexit.register(shutil.rmtree, _STATE, ignore_errors=True)
os.environ["PIPELINEKIT_STATE_DIR"] = _STATE
os.environ.pop("PIPELINEKIT_LOG", None)
