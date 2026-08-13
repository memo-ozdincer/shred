"""Public Python API for SHRED workload profiling."""

from lean_prefix import __version__
from shred.manifest import ManifestError, create_manifest
from shred.profiler import (
    ProfileConfig,
    ProfileResult,
    ShredProfileError,
    profile_workload,
    recommend_profile,
)

__all__ = [
    "ProfileConfig",
    "ProfileResult",
    "ShredProfileError",
    "ManifestError",
    "__version__",
    "profile_workload",
    "recommend_profile",
    "create_manifest",
]
