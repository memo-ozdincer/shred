"""Public Python API for SHRED workload profiling and trace screening."""

from lean_prefix import __version__
from lean_prefix.authentic_trace import (
    AuthenticTraceError,
    screen_authentic_trace,
    seal_authentic_trace,
)
from shred.manifest import ManifestError, create_manifest
from shred.oprover_adapter import (
    CpuBoundary,
    OProverAdapterError,
    split_boundary_stderr,
    summarize_cpu_boundaries,
)
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
    "AuthenticTraceError",
    "__version__",
    "profile_workload",
    "recommend_profile",
    "create_manifest",
    "CpuBoundary",
    "OProverAdapterError",
    "screen_authentic_trace",
    "seal_authentic_trace",
    "split_boundary_stderr",
    "summarize_cpu_boundaries",
]
