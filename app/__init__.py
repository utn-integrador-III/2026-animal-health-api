"""Animal Health Backend App."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_schemas_path = Path(__file__).with_name("schemas.py")
_schemas_spec = spec_from_file_location("app.schemas", _schemas_path)
if _schemas_spec and _schemas_spec.loader:
    schemas = module_from_spec(_schemas_spec)
    sys.modules["app.schemas"] = schemas
    _schemas_spec.loader.exec_module(schemas)
else:
    raise ImportError("Could not load app.schemas module")
