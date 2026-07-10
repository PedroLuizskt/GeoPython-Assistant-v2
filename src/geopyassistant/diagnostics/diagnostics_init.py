"""
Subpacote `diagnostics`: contrato e implementacao do diagnostico geoespacial.

Este modulo expoe o API publico do subpacote. Importe daqui em vez de
referenciar `schema` diretamente:

    from geopyassistant.diagnostics import VectorDiagnostic, GeospatialDiagnostic
"""

from geopyassistant.diagnostics.schema import (
    DIAGNOSTIC_SCHEMA_VERSION,
    AttributeField,
    AttributeSchema,
    BandInfo,
    BandStatistics,
    BoundingBox,
    ColorInterpretation,
    CRSInfo,
    FeatureInfo,
    GeometryInfo,
    GeospatialDiagnostic,
    OGCGeometryType,
    RasterDiagnostic,
    RasterFileFormat,
    RasterSpatialInfo,
    TopologyInfo,
    VectorDiagnostic,
    VectorFileFormat,
)
from geopyassistant.diagnostics.vector_profiler import (
    UnreadableFileError,
    UnsupportedFormatError,
    VectorProfiler,
    VectorProfilerConfig,
    VectorProfilerError,
    profile_vector_file,
)

__all__ = [
    "DIAGNOSTIC_SCHEMA_VERSION",
    "AttributeField",
    "AttributeSchema",
    "BandInfo",
    "BandStatistics",
    "BoundingBox",
    "CRSInfo",
    "ColorInterpretation",
    "FeatureInfo",
    "GeometryInfo",
    "GeospatialDiagnostic",
    "OGCGeometryType",
    "RasterDiagnostic",
    "RasterFileFormat",
    "RasterSpatialInfo",
    "TopologyInfo",
    "UnreadableFileError",
    "UnsupportedFormatError",
    "VectorDiagnostic",
    "VectorFileFormat",
    "VectorProfiler",
    "VectorProfilerConfig",
    "VectorProfilerError",
    "profile_vector_file",
]