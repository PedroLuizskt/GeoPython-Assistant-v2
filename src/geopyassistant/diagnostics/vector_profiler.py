"""
geopyassistant.diagnostics.vector_profiler
==========================================

Profiler estruturado para arquivos vetoriais geoespaciais.

Le um caminho para um arquivo vetorial (shapefile, GeoJSON, GeoPackage, etc.),
executa analise via GeoPandas/Shapely/PyProj, e produz um `VectorDiagnostic`
validado pelo contrato definido em `geopyassistant.diagnostics.schema`.

Filosofia de projeto
--------------------
O profiler segue tres principios de design:

1. **Separacao I/O vs analise**: o metodo publico `profile(path)` faz apenas o
   I/O do arquivo e delega para `analyze_dataframe(gdf, ...)`, que opera
   puramente sobre um `GeoDataFrame`. Isso viabiliza testes unitarios rapidos
   com fixtures em memoria.

2. **Warnings acumulativos**: qualidade do dado nao gera excecao. Problemas
   detectados (CRS ausente, geometrias invalidas, tipos misturados) sao
   acumulados em `quality_warnings`. Excecao so ocorre quando o arquivo nao
   pode ser lido de forma alguma.

3. **Marcadores padronizados de log**: mensagens de log usam o padrao
   `[OK]`, `[INFO]`, `[WARN]` conforme convencao adotada nos demais
   componentes do projeto.

Referencias
-----------
- GeoPandas User Guide: https://geopandas.org/en/stable/docs.html
- Shapely 2.x reference: https://shapely.readthedocs.io/en/stable/
- PyProj CRS: https://pyproj4.github.io/pyproj/stable/api/crs/crs.html
- OGC Simple Features Access: OGC 06-103r4, 2011.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import fiona
import geopandas as gpd
import pyproj

from geopyassistant.diagnostics.schema import (
    AttributeField,
    AttributeSchema,
    BoundingBox,
    CRSInfo,
    FeatureInfo,
    GeometryInfo,
    OGCGeometryType,
    TopologyInfo,
    VectorDiagnostic,
    VectorFileFormat,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes de proveniencia
# ---------------------------------------------------------------------------

PROFILER_NAME: Final[str] = "vector_profiler"
PROFILER_VERSION: Final[str] = "0.2.0"

# Mapeamento extensao -> formato do enum
_EXT_TO_FORMAT: Final[dict[str, VectorFileFormat]] = {
    ".shp": VectorFileFormat.SHAPEFILE,
    ".geojson": VectorFileFormat.GEOJSON,
    ".json": VectorFileFormat.GEOJSON,
    ".gpkg": VectorFileFormat.GEOPACKAGE,
    ".kml": VectorFileFormat.KML,
    ".gml": VectorFileFormat.GML,
    ".fgb": VectorFileFormat.FLATGEOBUF,
    ".parquet": VectorFileFormat.PARQUET,
}

# Mapeamento shapely geom_type -> OGCGeometryType
_SHAPELY_TO_OGC: Final[dict[str, OGCGeometryType]] = {
    "Point": OGCGeometryType.POINT,
    "LineString": OGCGeometryType.LINESTRING,
    "LinearRing": OGCGeometryType.LINESTRING,  # Aproximacao pragmatica
    "Polygon": OGCGeometryType.POLYGON,
    "MultiPoint": OGCGeometryType.MULTIPOINT,
    "MultiLineString": OGCGeometryType.MULTILINESTRING,
    "MultiPolygon": OGCGeometryType.MULTIPOLYGON,
    "GeometryCollection": OGCGeometryType.GEOMETRYCOLLECTION,
}


# ---------------------------------------------------------------------------
# Excecoes especializadas
# ---------------------------------------------------------------------------


class VectorProfilerError(Exception):
    """Erro base do modulo `vector_profiler`."""


class UnsupportedFormatError(VectorProfilerError):
    """Extensao de arquivo nao mapeada para nenhum formato suportado."""


class UnreadableFileError(VectorProfilerError):
    """Arquivo existe mas nao pode ser lido pelo backend Fiona/GeoPandas."""


# ---------------------------------------------------------------------------
# Configuracao imutavel do profiler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VectorProfilerConfig:
    """
    Parametros de configuracao do profiler vetorial.

    Attributes
    ----------
    compute_topology : bool
        Executa verificacoes topologicas (is_valid, is_empty) por feicao.
    compute_duplicates : bool
        Verifica duplicatas exatas de geometria. Custoso em camadas grandes;
        desligado por padrao.
    sample_size : int
        Numero maximo de valores amostrais textualizados por campo.
    """

    compute_topology: bool = True
    compute_duplicates: bool = False
    sample_size: int = 5


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------


class VectorProfiler:
    """
    Profiler que produz `VectorDiagnostic` a partir de arquivos vetoriais.

    Examples
    --------
    >>> profiler = VectorProfiler()
    >>> diag = profiler.profile("talhoes.shp")
    >>> print(diag.features.total_count)
    """

    def __init__(self, config: VectorProfilerConfig | None = None) -> None:
        self.config = config or VectorProfilerConfig()

    # -- Metodo publico principal (I/O) --------------------------------------

    def profile(self, path: str | Path) -> VectorDiagnostic:
        """
        Le um arquivo vetorial e retorna o diagnostico validado.

        Parameters
        ----------
        path : str or Path
            Caminho para o arquivo vetorial.

        Returns
        -------
        VectorDiagnostic
            Diagnostico completo, validado pelo schema Pydantic.

        Raises
        ------
        UnsupportedFormatError
            Se a extensao nao esta em `_EXT_TO_FORMAT`.
        UnreadableFileError
            Se o arquivo nao pode ser aberto pelo backend Fiona.
        FileNotFoundError
            Se o caminho nao existe.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {path}")

        file_format = _detect_format(path)
        file_size = path.stat().st_size

        driver = _detect_driver(path)
        logger.info("[INFO] Lendo arquivo vetorial: %s (driver=%s)", path.name, driver)

        try:
            gdf: gpd.GeoDataFrame = gpd.read_file(path)
        except Exception as exc:
            raise UnreadableFileError(
                f"Falha ao ler {path.name} com o backend Fiona/GeoPandas: {exc}"
            ) from exc

        logger.info("[OK] Leitura concluida: %d feicoes.", len(gdf))

        return self.analyze_dataframe(
            gdf,
            file_name=path.name,
            file_size_bytes=file_size,
            driver=driver,
            file_format=file_format,
        )

    # -- Superficie testavel em memoria --------------------------------------

    def analyze_dataframe(
        self,
        gdf: gpd.GeoDataFrame,
        *,
        file_name: str,
        file_size_bytes: int,
        driver: str,
        file_format: VectorFileFormat,
    ) -> VectorDiagnostic:
        """
        Constroi um `VectorDiagnostic` a partir de um `GeoDataFrame` carregado.

        Este metodo nao toca em I/O, o que o torna adequado para testes com
        fixtures em memoria.
        """
        warnings: list[str] = []

        crs_info, crs_warnings = _extract_crs(gdf)
        warnings.extend(crs_warnings)

        geometry_info, geom_warnings = _extract_geometry_info(gdf)
        warnings.extend(geom_warnings)

        features_info = _extract_features_info(gdf)
        attributes = _extract_attributes(gdf, sample_size=self.config.sample_size)

        if self.config.compute_topology:
            topology_info, topo_warnings = _extract_topology(
                gdf, compute_duplicates=self.config.compute_duplicates
            )
            warnings.extend(topo_warnings)
        else:
            topology_info = TopologyInfo()

        bounds = _extract_bounds(gdf)
        if bounds is None:
            warnings.append(
                "[WARN] Camada sem geometrias validas para calculo de envoltoria."
            )

        return VectorDiagnostic(
            profiler=PROFILER_NAME,
            profiler_version=PROFILER_VERSION,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            driver=driver,
            file_format=file_format,
            crs=crs_info,
            geometry=geometry_info,
            features=features_info,
            attributes=attributes,
            topology=topology_info,
            bounds=bounds,
            quality_warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Funcoes auxiliares privadas
# ---------------------------------------------------------------------------


def _detect_format(path: Path) -> VectorFileFormat:
    """Determina o `VectorFileFormat` pela extensao do arquivo."""
    ext = path.suffix.lower()
    if ext not in _EXT_TO_FORMAT:
        raise UnsupportedFormatError(
            f"Extensao {ext!r} nao suportada. Extensoes conhecidas: "
            f"{sorted(_EXT_TO_FORMAT)}."
        )
    return _EXT_TO_FORMAT[ext]


def _detect_driver(path: Path) -> str:
    """
    Consulta o driver Fiona utilizado, com fallback para o nome do formato.

    A abertura por Fiona e leve (le apenas o cabecalho) e permite reportar
    ao usuario o nome canonico do driver (ex.: 'ESRI Shapefile', 'GeoJSON').
    """
    try:
        with fiona.open(path) as src:
            return src.driver or "unknown"
    except Exception:
        return path.suffix.lstrip(".").upper() or "unknown"


def _extract_crs(gdf: gpd.GeoDataFrame) -> tuple[CRSInfo | None, list[str]]:
    """
    Constroi `CRSInfo` a partir do CRS declarado no `GeoDataFrame`.

    Returns
    -------
    tuple[CRSInfo | None, list[str]]
        Instancia de `CRSInfo` ou `None` quando ausente, junto de eventuais
        warnings acumulados.
    """
    warnings: list[str] = []
    if gdf.crs is None:
        warnings.append(
            "[WARN] Arquivo sem CRS declarado. Operacoes espaciais podem "
            "estar incorretas ate que um CRS seja atribuido."
        )
        return None, warnings

    pcrs: pyproj.CRS = gdf.crs  # GeoPandas ja converte para pyproj.CRS
    auth = pcrs.to_authority()
    authority: str | None = None
    code: str | None = None
    if auth is not None:
        authority, code = auth

    axis_order: str | None = None
    units: str | None = None
    if pcrs.axis_info:
        axis_order = ",".join(a.direction.lower() for a in pcrs.axis_info)
        units = pcrs.axis_info[0].unit_name

    area_of_use = pcrs.area_of_use.name if pcrs.area_of_use else None

    info = CRSInfo(
        authority=authority,
        code=code,
        name=pcrs.name,
        wkt=pcrs.to_wkt(),
        is_projected=pcrs.is_projected,
        is_geographic=pcrs.is_geographic,
        units=units,
        axis_order=axis_order,
        area_of_use=area_of_use,
    )
    return info, warnings


def _extract_geometry_info(
    gdf: gpd.GeoDataFrame,
) -> tuple[GeometryInfo, list[str]]:
    """Sumariza o tipo geometrico predominante e detecta heterogeneidade."""
    warnings: list[str] = []
    non_null = gdf.geometry.dropna()

    if len(non_null) == 0:
        warnings.append("[WARN] Camada sem geometrias nao-nulas.")
        return (
            GeometryInfo(
                geometry_type=OGCGeometryType.UNKNOWN,
                is_mixed=False,
                has_z=False,
                has_m=False,
            ),
            warnings,
        )

    counts_raw = non_null.geom_type.value_counts().to_dict()
    counts: dict[str, int] = {str(k): int(v) for k, v in counts_raw.items()}
    is_mixed = len(counts) > 1

    if is_mixed:
        # Normaliza chaves via mapeamento OGC (Point, LineString, Polygon...)
        warnings.append(
            f"[WARN] Camada heterogenea com {len(counts)} tipos geometricos: "
            f"{sorted(counts)}."
        )
        geom_type = OGCGeometryType.MIXED
        types_distribution = counts
    else:
        raw_type = next(iter(counts))
        geom_type = _SHAPELY_TO_OGC.get(raw_type, OGCGeometryType.UNKNOWN)
        types_distribution = {}

    try:
        has_z = bool(non_null.has_z.any())
    except AttributeError:
        has_z = False
    try:
        has_m = bool(non_null.has_m.any())
    except AttributeError:
        has_m = False

    return (
        GeometryInfo(
            geometry_type=geom_type,
            is_mixed=is_mixed,
            types_distribution=types_distribution,
            has_z=has_z,
            has_m=has_m,
        ),
        warnings,
    )


def _extract_features_info(gdf: gpd.GeoDataFrame) -> FeatureInfo:
    """
    Contagem de feicoes seguindo a convencao adotada no schema.

    Notes
    -----
    `empty_count` do schema conta feicoes sem representacao espacial util
    (geometria nula OU vazia). A separacao fina fica para `TopologyInfo`.
    """
    total = len(gdf)
    if total == 0:
        return FeatureInfo(total_count=0, empty_count=0, invalid_count=0)

    is_null = gdf.geometry.isna()
    non_null = gdf.geometry[~is_null]
    is_empty = non_null.is_empty
    empty_count = int(is_null.sum()) + int(is_empty.sum())

    non_empty = non_null[~is_empty]
    invalid_count = int((~non_empty.is_valid).sum()) if len(non_empty) > 0 else 0

    return FeatureInfo(
        total_count=total,
        empty_count=empty_count,
        invalid_count=invalid_count,
    )


def _extract_attributes(gdf: gpd.GeoDataFrame, *, sample_size: int) -> AttributeSchema:
    """Extrai esquema de atributos, ignorando a coluna de geometria ativa."""
    geom_col = gdf.geometry.name
    fields: list[AttributeField] = []

    for col in gdf.columns:
        if col == geom_col:
            continue
        series = gdf[col]
        nullable = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        non_null_values = series.dropna().head(sample_size)
        # Amostras textualizadas com truncamento seguro
        samples = [str(v)[:120] for v in non_null_values]
        fields.append(
            AttributeField(
                name=str(col),
                dtype=str(series.dtype),
                nullable_count=nullable,
                unique_count=unique,
                sample_values=samples,
            )
        )
    return AttributeSchema(fields=fields)


def _extract_topology(
    gdf: gpd.GeoDataFrame, *, compute_duplicates: bool
) -> tuple[TopologyInfo, list[str]]:
    """Contagens topologicas usadas em `TopologyInfo` e warnings correlatos."""
    warnings: list[str] = []
    non_null = gdf.geometry.dropna()
    empty_count = int(non_null.is_empty.sum()) if len(non_null) > 0 else 0

    non_empty = non_null[~non_null.is_empty] if len(non_null) > 0 else non_null
    invalid_count = int((~non_empty.is_valid).sum()) if len(non_empty) > 0 else 0

    if invalid_count > 0:
        warnings.append(
            f"[WARN] {invalid_count} geometria(s) topologicamente invalida(s) "
            "detectadas. Considere aplicar `make_valid` do Shapely."
        )

    duplicates = 0
    if compute_duplicates and len(non_empty) > 1:
        # WKB para comparacao exata; hashing evita explosao de memoria
        wkb_hashes = non_empty.apply(lambda g: hash(g.wkb))
        duplicates = int(len(wkb_hashes) - wkb_hashes.nunique())
        if duplicates > 0:
            warnings.append(
                f"[WARN] {duplicates} par(es) de geometrias duplicadas detectados."
            )

    topology = TopologyInfo(
        invalid_geometries=invalid_count,
        empty_geometries=empty_count,
        duplicate_features=duplicates,
    )
    return topology, warnings


def _extract_bounds(gdf: gpd.GeoDataFrame) -> BoundingBox | None:
    """Envoltoria total do dataset, ignorando geometrias nulas ou vazias."""
    non_null = gdf.geometry.dropna()
    if len(non_null) == 0:
        return None
    non_empty = non_null[~non_null.is_empty]
    if len(non_empty) == 0:
        return None
    minx, miny, maxx, maxy = non_empty.total_bounds
    return BoundingBox(minx=float(minx), miny=float(miny), maxx=float(maxx), maxy=float(maxy))


# ---------------------------------------------------------------------------
# Funcao de conveniencia
# ---------------------------------------------------------------------------


def profile_vector_file(
    path: str | Path,
    *,
    compute_topology: bool = True,
    compute_duplicates: bool = False,
    sample_size: int = 5,
) -> VectorDiagnostic:
    """
    Atalho funcional equivalente a `VectorProfiler(config).profile(path)`.

    Parameters
    ----------
    path : str or Path
        Caminho para o arquivo vetorial.
    compute_topology : bool, default True
        Executa checagens topologicas por feicao.
    compute_duplicates : bool, default False
        Executa deteccao de duplicatas (custoso).
    sample_size : int, default 5
        Numero de valores amostrais por campo, entre 0 e 5.

    Returns
    -------
    VectorDiagnostic
    """
    config = VectorProfilerConfig(
        compute_topology=compute_topology,
        compute_duplicates=compute_duplicates,
        sample_size=sample_size,
    )
    return VectorProfiler(config).profile(path)


__all__ = [
    "PROFILER_NAME",
    "PROFILER_VERSION",
    "UnreadableFileError",
    "UnsupportedFormatError",
    "VectorProfiler",
    "VectorProfilerConfig",
    "VectorProfilerError",
    "profile_vector_file",
]