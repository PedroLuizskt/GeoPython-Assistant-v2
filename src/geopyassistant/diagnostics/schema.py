"""
geopyassistant.diagnostics.schema
=================================

Modelos Pydantic v2 que definem o contrato de diagnostico estruturado de
arquivos geoespaciais utilizado pelo GeoPython Assistant v2.

Visao geral
-----------
O sistema produz um unico tipo polimorfico `GeospatialDiagnostic`, que e a
uniao discriminada entre `VectorDiagnostic` e `RasterDiagnostic`. O campo
`kind` atua como tag discriminadora, permitindo serializacao/deserializacao
robusta em JSON e despacho polimorfico em tempo de execucao.

Cada diagnostico carrega:

1. Metadados de proveniencia (`diagnostic_version`, `generated_at`, `profiler`),
   essenciais para reprodutibilidade em contexto cientifico.
2. Bloco de identificacao do arquivo (`file_name`, `file_format`, `file_size_bytes`,
   `driver`).
3. Bloco de Sistema de Referencia de Coordenadas (`crs`), parcialmente opcional,
   pois arquivos podem ser entregues sem CRS declarado.
4. Bloco geometrico ou matricial especifico ao tipo.
5. Lista de `quality_warnings`, util para o LLM sinalizar problemas no dado.

Referencias teoricas
--------------------
- Open Geospatial Consortium (OGC). *Simple Features Access - Part 1: Common
  architecture*. OGC 06-103r4, 2011.
- ISO 19111:2019. *Geographic information - Referencing by coordinates*.
- Pydantic v2 documentation: https://docs.pydantic.dev/latest/

Convencao de versionamento
--------------------------
Versao do schema segue SemVer e e exposta em `DIAGNOSTIC_SCHEMA_VERSION`.
Mudancas com quebra de contrato exigem incremento da versao maior (MAJOR).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Versionamento do schema
# ---------------------------------------------------------------------------

DIAGNOSTIC_SCHEMA_VERSION: str = "0.2.0"
"""Versao corrente do contrato de diagnostico. Segue SemVer."""


# ---------------------------------------------------------------------------
# Vocabulario controlado (StrEnum)
# ---------------------------------------------------------------------------


class OGCGeometryType(StrEnum):
    """
    Tipos de geometria simples conforme OGC Simple Features.

    Inclui as variantes 2D padrao. Variantes Z (3D) e M (medida) sao expressas
    via flags booleanas em `GeometryInfo` (`has_z`, `has_m`), seguindo a
    pratica adotada pela maioria das bibliotecas modernas (Shapely 2, GDAL 3).
    """

    POINT = "Point"
    LINESTRING = "LineString"
    POLYGON = "Polygon"
    MULTIPOINT = "MultiPoint"
    MULTILINESTRING = "MultiLineString"
    MULTIPOLYGON = "MultiPolygon"
    GEOMETRYCOLLECTION = "GeometryCollection"
    MIXED = "Mixed"  # Camada heterogenea (uso interno do diagnostico)
    UNKNOWN = "Unknown"


class VectorFileFormat(StrEnum):
    """Formatos vetoriais suportados pela camada de ingestao."""

    SHAPEFILE = "shapefile"
    GEOJSON = "geojson"
    GEOPACKAGE = "gpkg"
    KML = "kml"
    GML = "gml"
    FLATGEOBUF = "fgb"
    PARQUET = "geoparquet"
    UNKNOWN = "unknown"


class RasterFileFormat(StrEnum):
    """Formatos matriciais suportados pela camada de ingestao."""

    GEOTIFF = "geotiff"
    COG = "cog"  # Cloud Optimized GeoTIFF
    NETCDF = "netcdf"
    HDF5 = "hdf5"
    ZARR = "zarr"
    JPEG2000 = "jp2"
    GRIB = "grib"
    UNKNOWN = "unknown"


class ColorInterpretation(StrEnum):
    """
    Interpretacao colorimetrica de bandas, conforme convencao GDAL.

    Empregada para indicar ao usuario quando uma banda representa um canal
    RGB, escala de cinza, indice categorico, mascara, etc.
    """

    GRAY = "gray"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    ALPHA = "alpha"
    PALETTE = "palette"
    UNDEFINED = "undefined"


# ---------------------------------------------------------------------------
# Configuracao base compartilhada por todos os modelos
# ---------------------------------------------------------------------------

_BASE_CONFIG = ConfigDict(
    extra="forbid",
    str_strip_whitespace=True,
    validate_assignment=True,
    frozen=False,
    use_enum_values=False,
)


class _StrictModel(BaseModel):
    """Classe base com configuracao Pydantic estrita compartilhada."""

    model_config = _BASE_CONFIG


# ---------------------------------------------------------------------------
# Modelos comuns: BoundingBox e CRSInfo
# ---------------------------------------------------------------------------


class BoundingBox(_StrictModel):
    """
    Envoltoria retangular axis-aligned no sistema de referencia do dataset.

    Notes
    -----
    A invariante `minx <= maxx` e `miny <= maxy` e garantida em runtime.
    Coordenadas seguem a ordem espacial cartografica (X = leste, Y = norte)
    independentemente da ordem de eixos do CRS, alinhando-se com a convencao
    adotada por GeoPandas (`total_bounds`).
    """

    minx: float = Field(description="Limite oeste (X minimo) no CRS do dataset.")
    miny: float = Field(description="Limite sul (Y minimo) no CRS do dataset.")
    maxx: float = Field(description="Limite leste (X maximo) no CRS do dataset.")
    maxy: float = Field(description="Limite norte (Y maximo) no CRS do dataset.")

    @model_validator(mode="after")
    def _check_axis_order(self) -> Self:
        if self.minx > self.maxx:
            raise ValueError(
                f"BoundingBox invalida: minx ({self.minx}) > maxx ({self.maxx})."
            )
        if self.miny > self.maxy:
            raise ValueError(
                f"BoundingBox invalida: miny ({self.miny}) > maxy ({self.maxy})."
            )
        return self

    @property
    def width(self) -> float:
        """Extensao horizontal no CRS nativo."""
        return self.maxx - self.minx

    @property
    def height(self) -> float:
        """Extensao vertical no CRS nativo."""
        return self.maxy - self.miny


class CRSInfo(_StrictModel):
    """
    Informacao sobre o Sistema de Referencia de Coordenadas (CRS) do dataset.

    Notes
    -----
    Quando o arquivo nao declara CRS, esta estrutura nao deve ser instanciada;
    o campo `crs` do diagnostico deve ser deixado como `None` e um aviso deve
    ser registrado em `quality_warnings`. Modelar a ausencia de CRS como `None`
    em vez de um `CRSInfo` "vazio" preserva a semantica esperada por
    `pyproj.CRS`.
    """

    authority: str | None = Field(
        default=None,
        description='Autoridade definidora (ex.: "EPSG", "ESRI", "IAU").',
    )
    code: str | None = Field(
        default=None,
        description="Codigo numerico no padrao da autoridade.",
    )
    name: str = Field(description="Nome canonico do CRS, conforme retornado por pyproj.")
    wkt: str = Field(
        description="Representacao WKT (Well-Known Text), serializacao canonica do CRS."
    )
    is_projected: bool = Field(description="Verdadeiro para CRS projetados.")
    is_geographic: bool = Field(description="Verdadeiro para CRS geograficos (lat/lon).")
    units: str | None = Field(default=None, description="Unidades lineares ou angulares.")
    axis_order: str | None = Field(
        default=None,
        description='Ordem dos eixos do CRS, ex.: "easting,northing" ou "latitude,longitude".',
    )
    area_of_use: str | None = Field(
        default=None,
        description="Descricao textual da area de validade do CRS, quando disponivel.",
    )

    @model_validator(mode="after")
    def _check_authority_code_consistency(self) -> Self:
        """
        Garante consistencia entre `authority` e `code`.

        Se um deles esta presente, o outro tambem deve estar. Para EPSG,
        verifica que o codigo e numerico, conforme registry oficial.
        """
        if (self.authority is None) != (self.code is None):
            raise ValueError(
                "Os campos `authority` e `code` devem ser ambos definidos ou ambos nulos."
            )
        if self.authority == "EPSG" and self.code is not None and not self.code.isdigit():
            raise ValueError(
                f"Codigo EPSG deve ser numerico, recebido: {self.code!r}."
            )
        if self.is_projected and self.is_geographic:
            raise ValueError("Um CRS nao pode ser simultaneamente projetado e geografico.")
        return self

    @property
    def urn(self) -> str | None:
        """Forma compacta `authority:code` (ex.: `EPSG:4326`), util para logs."""
        if self.authority and self.code:
            return f"{self.authority}:{self.code}"
        return None


# ---------------------------------------------------------------------------
# Modelos vetoriais
# ---------------------------------------------------------------------------


class GeometryInfo(_StrictModel):
    """Caracterizacao geometrica de uma camada vetorial."""

    geometry_type: OGCGeometryType = Field(
        description="Tipo geometrico predominante. `MIXED` indica heterogeneidade."
    )
    is_mixed: bool = Field(
        default=False,
        description="Verdadeiro quando a camada apresenta mais de um tipo de geometria.",
    )
    types_distribution: dict[str, NonNegativeInt] = Field(
        default_factory=dict,
        description="Contagem por tipo de geometria, preenchida quando `is_mixed` e verdadeiro.",
    )
    has_z: bool = Field(default=False, description="Geometrias com coordenada Z (3D).")
    has_m: bool = Field(default=False, description="Geometrias com coordenada de medida M.")

    @model_validator(mode="after")
    def _check_mixed_consistency(self) -> Self:
        if self.is_mixed and not self.types_distribution:
            raise ValueError(
                "Quando `is_mixed` e verdadeiro, `types_distribution` nao pode estar vazio."
            )
        if not self.is_mixed and len(self.types_distribution) > 1:
            raise ValueError(
                "`types_distribution` com mais de um tipo exige `is_mixed=True`."
            )
        return self


class FeatureInfo(_StrictModel):
    """Sumario contagem de feicoes."""

    total_count: NonNegativeInt = Field(description="Numero total de feicoes na camada.")
    empty_count: NonNegativeInt = Field(
        default=0,
        description="Feicoes sem geometria associada (geometria nula).",
    )
    invalid_count: NonNegativeInt = Field(
        default=0,
        description="Feicoes com geometria invalida segundo OGC SFS (auto-intersecoes, etc.).",
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.empty_count + self.invalid_count > self.total_count:
            raise ValueError(
                "A soma de `empty_count` e `invalid_count` nao pode exceder `total_count`."
            )
        return self


class AttributeField(_StrictModel):
    """Descritor de um campo (coluna) da tabela de atributos."""

    name: str = Field(description="Nome do campo conforme declarado no arquivo.")
    dtype: str = Field(
        description='Tipo de dado nativo, ex.: "int64", "float64", "object", "datetime64[ns]".'
    )
    nullable_count: NonNegativeInt = Field(
        default=0, description="Quantidade de registros com valor nulo neste campo."
    )
    unique_count: NonNegativeInt = Field(
        default=0, description="Cardinalidade do campo (quantidade de valores distintos)."
    )
    sample_values: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Ate cinco amostras textualizadas, uteis para contexto no LLM.",
    )


class AttributeSchema(_StrictModel):
    """Conjunto ordenado de campos da tabela de atributos."""

    fields: list[AttributeField] = Field(
        default_factory=list,
        description="Lista ordenada de campos, preservando a ordem declarada no arquivo.",
    )

    @property
    def field_count(self) -> int:
        """Numero total de campos."""
        return len(self.fields)


class TopologyInfo(_StrictModel):
    """Indicadores de qualidade topologica da camada."""

    invalid_geometries: NonNegativeInt = Field(
        default=0,
        description="Feicoes que falham em `is_valid` do GEOS/Shapely.",
    )
    empty_geometries: NonNegativeInt = Field(
        default=0, description="Feicoes com geometria vazia (mas presente)."
    )
    duplicate_features: NonNegativeInt = Field(
        default=0,
        description="Pares de feicoes com geometria identica (deteccao opcional).",
    )


# ---------------------------------------------------------------------------
# Modelos matriciais
# ---------------------------------------------------------------------------


class RasterSpatialInfo(_StrictModel):
    """Caracterizacao espacial de um dataset matricial."""

    width: PositiveInt = Field(description="Numero de colunas (pixels na direcao X).")
    height: PositiveInt = Field(description="Numero de linhas (pixels na direcao Y).")
    transform: list[float] = Field(
        min_length=6,
        max_length=6,
        description=(
            "Coeficientes da transformacao afim no formato GDAL: "
            "[a, b, c, d, e, f]. Mapeia (col, row) em (x, y) do CRS."
        ),
    )
    resolution_x: NonNegativeFloat = Field(
        description="Tamanho de pixel no eixo X, nas unidades do CRS."
    )
    resolution_y: NonNegativeFloat = Field(
        description="Tamanho de pixel no eixo Y, nas unidades do CRS (valor absoluto)."
    )
    bounds: BoundingBox = Field(description="Envoltoria geografica do raster.")

    @property
    def pixel_count(self) -> int:
        """Total de pixels por banda."""
        return self.width * self.height


class BandStatistics(_StrictModel):
    """Estatisticas descritivas calculadas sobre os pixels validos de uma banda."""

    min: float = Field(description="Valor minimo observado entre pixels validos.")
    max: float = Field(description="Valor maximo observado entre pixels validos.")
    mean: float = Field(description="Media aritmetica dos pixels validos.")
    std: NonNegativeFloat = Field(description="Desvio padrao amostral.")
    valid_count: NonNegativeInt = Field(
        description="Pixels que nao foram identificados como nodata."
    )
    nodata_count: NonNegativeInt = Field(
        default=0, description="Pixels iguais ao valor de nodata declarado."
    )
    percentiles: dict[str, float] = Field(
        default_factory=dict,
        description='Percentis opcionais, ex.: {"p25": ..., "p50": ..., "p75": ...}.',
    )

    @model_validator(mode="after")
    def _check_statistical_order(self) -> Self:
        if not (self.min <= self.mean <= self.max):
            raise ValueError(
                f"Inconsistencia estatistica: min ({self.min}) <= mean ({self.mean}) "
                f"<= max ({self.max}) violada."
            )
        return self


class BandInfo(_StrictModel):
    """Descritor de uma banda individual do raster."""

    index: PositiveInt = Field(
        description="Indice da banda (1-based), conforme convencao do rasterio e GDAL."
    )
    dtype: str = Field(
        description='Tipo numerico do pixel, ex.: "uint8", "uint16", "int16", "float32".'
    )
    nodata: float | None = Field(
        default=None,
        description="Valor declarado como nodata para esta banda. `None` significa nao declarado.",
    )
    description: str | None = Field(
        default=None,
        description='Descricao textual, ex.: "Reflectancia na banda do vermelho".',
    )
    statistics: BandStatistics | None = Field(
        default=None,
        description="Estatisticas opcionais. Nulo em diagnosticos rasos sem amostragem.",
    )
    color_interpretation: ColorInterpretation = Field(
        default=ColorInterpretation.UNDEFINED,
        description="Interpretacao colorimetrica conforme convencao GDAL.",
    )
    is_categorical: bool = Field(
        default=False,
        description="Verdadeiro quando a banda representa categorias discretas (uso do solo).",
    )
    categories: list[int | float] | None = Field(
        default=None,
        description="Categorias unicas, preenchidas apenas quando `is_categorical` e verdadeiro.",
    )

    @model_validator(mode="after")
    def _check_categorical_consistency(self) -> Self:
        if self.is_categorical and not self.categories:
            raise ValueError(
                "Banda marcada como categorica deve apresentar `categories` nao vazia."
            )
        if not self.is_categorical and self.categories:
            raise ValueError(
                "`categories` so deve ser preenchido quando `is_categorical=True`."
            )
        return self


# ---------------------------------------------------------------------------
# Diagnosticos completos (modelos de topo)
# ---------------------------------------------------------------------------


class _DiagnosticBase(_StrictModel):
    """Campos comuns a todos os diagnosticos (proveniencia e identidade do arquivo)."""

    # Proveniencia
    diagnostic_version: str = Field(
        default=DIAGNOSTIC_SCHEMA_VERSION,
        description="Versao do contrato de diagnostico utilizada.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Instante UTC em que o diagnostico foi produzido (ISO 8601).",
    )
    profiler: str = Field(
        description='Identificador do profiler responsavel, ex.: "vector_profiler".'
    )
    profiler_version: str = Field(
        description="Versao do profiler, util para reproducibilidade."
    )

    # Identidade do arquivo
    file_name: str = Field(description="Nome do arquivo conforme submetido pelo usuario.")
    file_size_bytes: NonNegativeInt = Field(description="Tamanho em bytes.")
    driver: str = Field(description="Driver de leitura utilizado (ex.: ESRI Shapefile, GTiff).")

    # CRS (pode ser ausente)
    crs: CRSInfo | None = Field(
        default=None,
        description="Sistema de referencia. `None` indica arquivo sem CRS declarado.",
    )

    # Avisos
    quality_warnings: list[str] = Field(
        default_factory=list,
        description="Mensagens de aviso identificadas durante o profiling.",
    )

    @field_validator("file_name")
    @classmethod
    def _file_name_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("`file_name` nao pode ser vazio.")
        return v


class VectorDiagnostic(_DiagnosticBase):
    """Diagnostico completo de um arquivo vetorial."""

    kind: Literal["vector"] = Field(
        default="vector",
        description="Tag discriminadora da uniao `GeospatialDiagnostic`.",
    )
    file_format: VectorFileFormat = Field(description="Formato vetorial detectado.")
    geometry: GeometryInfo = Field(description="Sumario geometrico da camada.")
    features: FeatureInfo = Field(description="Contagens de feicoes.")
    attributes: AttributeSchema = Field(description="Esquema da tabela de atributos.")
    topology: TopologyInfo = Field(
        default_factory=TopologyInfo,
        description="Indicadores de qualidade topologica.",
    )
    bounds: BoundingBox | None = Field(
        default=None,
        description="Envoltoria total. Nulo quando a camada nao possui geometrias validas.",
    )


class RasterDiagnostic(_DiagnosticBase):
    """Diagnostico completo de um arquivo matricial."""

    kind: Literal["raster"] = Field(
        default="raster",
        description="Tag discriminadora da uniao `GeospatialDiagnostic`.",
    )
    file_format: RasterFileFormat = Field(description="Formato matricial detectado.")
    spatial: RasterSpatialInfo = Field(description="Sumario espacial do raster.")
    bands: list[BandInfo] = Field(
        min_length=1,
        description="Descritores das bandas (1-based). Pelo menos uma banda e obrigatoria.",
    )
    dataset_nodata: float | None = Field(
        default=None,
        description="Valor de nodata declarado no nivel do dataset (pode diferir por banda).",
    )
    compression: str | None = Field(
        default=None,
        description='Algoritmo de compressao, ex.: "DEFLATE", "LZW", "ZSTD".',
    )
    is_cog: bool = Field(
        default=False,
        description="Verdadeiro quando o GeoTIFF segue o perfil Cloud Optimized.",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Metadados GDAL chave-valor anexados ao dataset.",
    )

    @property
    def band_count(self) -> int:
        """Numero de bandas detectadas."""
        return len(self.bands)


# ---------------------------------------------------------------------------
# Uniao discriminada
# ---------------------------------------------------------------------------


GeospatialDiagnostic = Annotated[
    VectorDiagnostic | RasterDiagnostic,
    Field(discriminator="kind"),
]
"""
Tipo polimorfico de topo do sistema.

Pydantic seleciona automaticamente a variante adequada com base no campo
discriminador `kind`. Use este tipo em assinaturas de funcoes que operam
indistintamente sobre diagnosticos vetoriais e matriciais.
"""


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
    "VectorDiagnostic",
    "VectorFileFormat",
]
