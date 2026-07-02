"""
Testes unitarios do contrato de diagnostico geoespacial.

Cobertura:
    * Construcao valida de cada modelo do schema.
    * Invariantes semanticas (BoundingBox, BandStatistics, CRSInfo).
    * Discriminated union `GeospatialDiagnostic` em parsing/serializacao JSON.
    * Round-trip JSON sem perda de informacao.
    * Imutabilidade do versionamento.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wgs84() -> CRSInfo:
    return CRSInfo(
        authority="EPSG",
        code="4326",
        name="WGS 84",
        wkt='GEOGCS["WGS 84", ... ]',  # WKT simplificado para teste
        is_projected=False,
        is_geographic=True,
        units="degree",
        axis_order="latitude,longitude",
        area_of_use="World",
    )


def _sirgas2000_utm23s() -> CRSInfo:
    return CRSInfo(
        authority="EPSG",
        code="31983",
        name="SIRGAS 2000 / UTM zone 23S",
        wkt='PROJCS["SIRGAS 2000 / UTM zone 23S", ... ]',
        is_projected=True,
        is_geographic=False,
        units="metre",
        axis_order="easting,northing",
        area_of_use="Brazil - between 48W and 42W, southern hemisphere",
    )


def _valid_vector_diagnostic() -> VectorDiagnostic:
    return VectorDiagnostic(
        profiler="vector_profiler",
        profiler_version="0.2.0",
        file_name="talhoes.shp",
        file_size_bytes=1_524_300,
        driver="ESRI Shapefile",
        file_format=VectorFileFormat.SHAPEFILE,
        crs=_sirgas2000_utm23s(),
        geometry=GeometryInfo(
            geometry_type=OGCGeometryType.POLYGON,
            is_mixed=False,
            has_z=False,
            has_m=False,
        ),
        features=FeatureInfo(total_count=312, empty_count=0, invalid_count=2),
        attributes=AttributeSchema(
            fields=[
                AttributeField(
                    name="id_talhao",
                    dtype="int64",
                    nullable_count=0,
                    unique_count=312,
                    sample_values=["1", "2", "3"],
                ),
                AttributeField(
                    name="especie",
                    dtype="object",
                    nullable_count=4,
                    unique_count=3,
                    sample_values=["Eucalyptus urograndis", "Pinus elliottii"],
                ),
            ]
        ),
        topology=TopologyInfo(invalid_geometries=2),
        bounds=BoundingBox(minx=200000.0, miny=7500000.0, maxx=250000.0, maxy=7600000.0),
    )


def _valid_raster_diagnostic() -> RasterDiagnostic:
    return RasterDiagnostic(
        profiler="raster_profiler",
        profiler_version="0.2.0",
        file_name="ndvi_sentinel2.tif",
        file_size_bytes=85_000_000,
        driver="GTiff",
        file_format=RasterFileFormat.COG,
        crs=_wgs84(),
        spatial=RasterSpatialInfo(
            width=10980,
            height=10980,
            transform=[10.0, 0.0, 600000.0, 0.0, -10.0, 7800000.0],
            resolution_x=10.0,
            resolution_y=10.0,
            bounds=BoundingBox(
                minx=600000.0, miny=7690200.0, maxx=709800.0, maxy=7800000.0
            ),
        ),
        bands=[
            BandInfo(
                index=1,
                dtype="float32",
                nodata=-9999.0,
                description="Normalized Difference Vegetation Index",
                statistics=BandStatistics(
                    min=-0.32,
                    max=0.91,
                    mean=0.54,
                    std=0.18,
                    valid_count=100_000_000,
                    nodata_count=200_000,
                ),
                color_interpretation=ColorInterpretation.GRAY,
            )
        ],
        is_cog=True,
        compression="DEFLATE",
        tags={"AREA_OR_POINT": "Area"},
    )


# ---------------------------------------------------------------------------
# BoundingBox
# ---------------------------------------------------------------------------


class TestBoundingBox:
    def test_constroi_caixa_valida(self) -> None:
        bbox = BoundingBox(minx=0.0, miny=0.0, maxx=10.0, maxy=20.0)
        assert bbox.width == 10.0
        assert bbox.height == 20.0

    def test_rejeita_minx_maior_que_maxx(self) -> None:
        with pytest.raises(ValidationError, match="minx"):
            BoundingBox(minx=10.0, miny=0.0, maxx=5.0, maxy=20.0)

    def test_rejeita_miny_maior_que_maxy(self) -> None:
        with pytest.raises(ValidationError, match="miny"):
            BoundingBox(minx=0.0, miny=30.0, maxx=10.0, maxy=20.0)

    def test_aceita_caixa_degenerada(self) -> None:
        bbox = BoundingBox(minx=5.0, miny=5.0, maxx=5.0, maxy=5.0)
        assert bbox.width == 0.0
        assert bbox.height == 0.0


# ---------------------------------------------------------------------------
# CRSInfo
# ---------------------------------------------------------------------------


class TestCRSInfo:
    def test_constroi_crs_geografico(self) -> None:
        crs = _wgs84()
        assert crs.urn == "EPSG:4326"
        assert crs.is_geographic is True

    def test_constroi_crs_projetado(self) -> None:
        crs = _sirgas2000_utm23s()
        assert crs.urn == "EPSG:31983"
        assert crs.is_projected is True

    def test_rejeita_projecao_e_geografico_simultaneos(self) -> None:
        with pytest.raises(ValidationError, match="simultaneamente"):
            CRSInfo(
                authority="EPSG",
                code="4326",
                name="WGS 84",
                wkt="...",
                is_projected=True,
                is_geographic=True,
            )

    def test_rejeita_authority_sem_code(self) -> None:
        with pytest.raises(ValidationError, match="ambos definidos"):
            CRSInfo(
                authority="EPSG",
                code=None,
                name="WGS 84",
                wkt="...",
                is_projected=False,
                is_geographic=True,
            )

    def test_rejeita_codigo_epsg_nao_numerico(self) -> None:
        with pytest.raises(ValidationError, match="numerico"):
            CRSInfo(
                authority="EPSG",
                code="EPSG:4326",  # Erro tipico
                name="WGS 84",
                wkt="...",
                is_projected=False,
                is_geographic=True,
            )

    def test_urn_nulo_quando_authority_ausente(self) -> None:
        crs = CRSInfo(
            authority=None,
            code=None,
            name="Custom CRS",
            wkt="...",
            is_projected=False,
            is_geographic=True,
        )
        assert crs.urn is None


# ---------------------------------------------------------------------------
# GeometryInfo
# ---------------------------------------------------------------------------


class TestGeometryInfo:
    def test_constroi_geometria_homogenea(self) -> None:
        info = GeometryInfo(geometry_type=OGCGeometryType.POLYGON)
        assert info.is_mixed is False
        assert info.has_z is False

    def test_mixed_exige_types_distribution(self) -> None:
        with pytest.raises(ValidationError, match="types_distribution"):
            GeometryInfo(geometry_type=OGCGeometryType.MIXED, is_mixed=True)

    def test_types_distribution_exige_mixed(self) -> None:
        with pytest.raises(ValidationError, match="is_mixed=True"):
            GeometryInfo(
                geometry_type=OGCGeometryType.POLYGON,
                is_mixed=False,
                types_distribution={"Polygon": 10, "Point": 5},
            )

    def test_mixed_coerente(self) -> None:
        info = GeometryInfo(
            geometry_type=OGCGeometryType.MIXED,
            is_mixed=True,
            types_distribution={"Polygon": 8, "LineString": 3},
        )
        assert sum(info.types_distribution.values()) == 11


# ---------------------------------------------------------------------------
# FeatureInfo
# ---------------------------------------------------------------------------


class TestFeatureInfo:
    def test_constroi_contagem_valida(self) -> None:
        f = FeatureInfo(total_count=100, empty_count=2, invalid_count=3)
        assert f.total_count == 100

    def test_rejeita_soma_excessiva(self) -> None:
        with pytest.raises(ValidationError, match="nao pode exceder"):
            FeatureInfo(total_count=10, empty_count=8, invalid_count=5)

    def test_aceita_contagens_zeradas(self) -> None:
        f = FeatureInfo(total_count=0)
        assert f.empty_count == 0
        assert f.invalid_count == 0


# ---------------------------------------------------------------------------
# AttributeField e AttributeSchema
# ---------------------------------------------------------------------------


class TestAttributeSchema:
    def test_field_count_e_propriedade_derivada(self) -> None:
        schema = AttributeSchema(
            fields=[
                AttributeField(name="a", dtype="int64"),
                AttributeField(name="b", dtype="object"),
            ]
        )
        assert schema.field_count == 2

    def test_sample_values_limitado_em_cinco(self) -> None:
        with pytest.raises(ValidationError):
            AttributeField(
                name="x",
                dtype="object",
                sample_values=["a", "b", "c", "d", "e", "f"],
            )


# ---------------------------------------------------------------------------
# BandStatistics
# ---------------------------------------------------------------------------


class TestBandStatistics:
    def test_constroi_estatisticas_validas(self) -> None:
        stats = BandStatistics(
            min=0.0, max=1.0, mean=0.5, std=0.2, valid_count=1000, nodata_count=10
        )
        assert stats.mean == 0.5

    def test_rejeita_mean_fora_do_intervalo(self) -> None:
        with pytest.raises(ValidationError, match="Inconsistencia estatistica"):
            BandStatistics(min=0.0, max=1.0, mean=2.0, std=0.2, valid_count=1000)

    def test_rejeita_std_negativo(self) -> None:
        with pytest.raises(ValidationError):
            BandStatistics(min=0.0, max=1.0, mean=0.5, std=-0.1, valid_count=1000)


# ---------------------------------------------------------------------------
# BandInfo
# ---------------------------------------------------------------------------


class TestBandInfo:
    def test_banda_contigua_constroi(self) -> None:
        band = BandInfo(index=1, dtype="float32")
        assert band.is_categorical is False
        assert band.color_interpretation is ColorInterpretation.UNDEFINED

    def test_categorica_exige_categories(self) -> None:
        with pytest.raises(ValidationError, match="nao vazia"):
            BandInfo(index=1, dtype="uint8", is_categorical=True)

    def test_categories_exige_flag_categorical(self) -> None:
        with pytest.raises(ValidationError, match="is_categorical=True"):
            BandInfo(index=1, dtype="uint8", categories=[1, 2, 3])


# ---------------------------------------------------------------------------
# Diagnosticos completos
# ---------------------------------------------------------------------------


class TestVectorDiagnostic:
    def test_constroi_diagnostico_completo(self) -> None:
        diag = _valid_vector_diagnostic()
        assert diag.kind == "vector"
        assert diag.diagnostic_version == DIAGNOSTIC_SCHEMA_VERSION
        assert isinstance(diag.generated_at, datetime)
        assert diag.generated_at.tzinfo == UTC
        assert diag.features.total_count == 312

    def test_atributos_padrao_e_warnings(self) -> None:
        diag = _valid_vector_diagnostic()
        assert diag.quality_warnings == []
        assert diag.topology.duplicate_features == 0

    def test_file_name_nao_pode_ser_vazio(self) -> None:
        with pytest.raises(ValidationError, match="file_name"):
            VectorDiagnostic(
                profiler="vector_profiler",
                profiler_version="0.2.0",
                file_name="",
                file_size_bytes=10,
                driver="ESRI Shapefile",
                file_format=VectorFileFormat.SHAPEFILE,
                geometry=GeometryInfo(geometry_type=OGCGeometryType.POLYGON),
                features=FeatureInfo(total_count=1),
                attributes=AttributeSchema(),
            )


class TestRasterDiagnostic:
    def test_constroi_diagnostico_completo(self) -> None:
        diag = _valid_raster_diagnostic()
        assert diag.kind == "raster"
        assert diag.band_count == 1
        assert diag.is_cog is True

    def test_exige_pelo_menos_uma_banda(self) -> None:
        with pytest.raises(ValidationError, match="at least 1 item"):
            RasterDiagnostic(
                profiler="raster_profiler",
                profiler_version="0.2.0",
                file_name="empty.tif",
                file_size_bytes=100,
                driver="GTiff",
                file_format=RasterFileFormat.GEOTIFF,
                spatial=RasterSpatialInfo(
                    width=10,
                    height=10,
                    transform=[1.0, 0.0, 0.0, 0.0, -1.0, 0.0],
                    resolution_x=1.0,
                    resolution_y=1.0,
                    bounds=BoundingBox(minx=0, miny=0, maxx=10, maxy=10),
                ),
                bands=[],
            )


# ---------------------------------------------------------------------------
# Uniao discriminada
# ---------------------------------------------------------------------------


class TestGeospatialDiagnosticUnion:
    def _adapter(self) -> TypeAdapter[GeospatialDiagnostic]:
        return TypeAdapter(GeospatialDiagnostic)

    def test_parse_vector_pelo_kind(self) -> None:
        adapter = self._adapter()
        payload = _valid_vector_diagnostic().model_dump(mode="json")
        parsed = adapter.validate_python(payload)
        assert isinstance(parsed, VectorDiagnostic)

    def test_parse_raster_pelo_kind(self) -> None:
        adapter = self._adapter()
        payload = _valid_raster_diagnostic().model_dump(mode="json")
        parsed = adapter.validate_python(payload)
        assert isinstance(parsed, RasterDiagnostic)

    def test_kind_invalido_eh_rejeitado(self) -> None:
        adapter = self._adapter()
        payload = _valid_vector_diagnostic().model_dump(mode="json")
        payload["kind"] = "trajetoria"  # nao existe
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


# ---------------------------------------------------------------------------
# Round-trip JSON
# ---------------------------------------------------------------------------


class TestRoundTripJSON:
    def test_vetor_roundtrip(self) -> None:
        original = _valid_vector_diagnostic()
        as_json = original.model_dump_json()
        reconstructed = VectorDiagnostic.model_validate_json(as_json)
        assert reconstructed == original

    def test_raster_roundtrip(self) -> None:
        original = _valid_raster_diagnostic()
        as_json = original.model_dump_json()
        reconstructed = RasterDiagnostic.model_validate_json(as_json)
        assert reconstructed == original

    def test_payload_eh_json_serializavel_padrao(self) -> None:
        """Garante que o dump usa apenas tipos JSON nativos."""
        diag = _valid_vector_diagnostic()
        as_json = diag.model_dump_json()
        # Deve ser parseavel pelo json stdlib sem custom decoder
        parsed = json.loads(as_json)
        assert parsed["kind"] == "vector"
        assert parsed["diagnostic_version"] == DIAGNOSTIC_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Schema JSON exportavel (uso documental)
# ---------------------------------------------------------------------------


class TestExportedJSONSchema:
    def test_vector_json_schema_contains_discriminator(self) -> None:
        schema = VectorDiagnostic.model_json_schema()
        assert "kind" in schema["properties"]

    def test_raster_json_schema_contains_band_array(self) -> None:
        schema = RasterDiagnostic.model_json_schema()
        assert schema["properties"]["bands"]["type"] == "array"
