"""
Testes do `VectorProfiler`.

Cobertura em duas camadas:

* **Unitaria**: exercita `analyze_dataframe(gdf, ...)` sobre fixtures Shapely
  em memoria. Rapida e determinista.
* **Integracao**: exercita `profile(path)` sobre arquivos gravados em
  `tmp_path`, cobrindo o loop completo I/O -> parsing -> analise.

Marcadores `@pytest.mark.integration` sao usados nos testes de I/O.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest

from geopyassistant.diagnostics import (
    OGCGeometryType,
    VectorDiagnostic,
    VectorFileFormat,
    VectorProfiler,
    VectorProfilerConfig,
    profile_vector_file,
)
from geopyassistant.diagnostics.vector_profiler import (
    PROFILER_NAME,
    PROFILER_VERSION,
    UnsupportedFormatError,
    _detect_format,
    _extract_attributes,
    _extract_bounds,
    _extract_crs,
    _extract_features_info,
    _extract_geometry_info,
    _extract_topology,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(gdf: gpd.GeoDataFrame, **overrides: object) -> VectorDiagnostic:
    """Atalho: analisa `gdf` com meta padrao, permitindo overrides pontuais."""
    profiler = VectorProfiler()
    meta = {
        "file_name": "memoria.geojson",
        "file_size_bytes": 1024,
        "driver": "in-memory",
        "file_format": VectorFileFormat.GEOJSON,
    } | overrides
    return profiler.analyze_dataframe(gdf, **meta)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Deteccao de formato
# ---------------------------------------------------------------------------


class TestDetectFormat:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("talhoes.shp", VectorFileFormat.SHAPEFILE),
            ("parcelas.geojson", VectorFileFormat.GEOJSON),
            ("dados.json", VectorFileFormat.GEOJSON),
            ("mapa.gpkg", VectorFileFormat.GEOPACKAGE),
            ("rota.kml", VectorFileFormat.KML),
            ("dados.fgb", VectorFileFormat.FLATGEOBUF),
            ("SHAPE.SHP", VectorFileFormat.SHAPEFILE),  # Case-insensitive
        ],
    )
    def test_extensoes_reconhecidas(self, path: str, expected: VectorFileFormat) -> None:
        assert _detect_format(Path(path)) is expected

    def test_extensao_desconhecida_levanta(self) -> None:
        with pytest.raises(UnsupportedFormatError, match="nao suportada"):
            _detect_format(Path("dados.xyz"))


# ---------------------------------------------------------------------------
# Extracao de CRS
# ---------------------------------------------------------------------------


class TestExtractCRS:
    def test_sirgas_projetado(self, gdf_polygons_sirgas: gpd.GeoDataFrame) -> None:
        crs, warnings = _extract_crs(gdf_polygons_sirgas)
        assert crs is not None
        assert crs.authority == "EPSG"
        assert crs.code == "31983"
        assert crs.is_projected is True
        assert crs.is_geographic is False
        assert crs.units == "metre"
        assert crs.urn == "EPSG:31983"
        assert warnings == []

    def test_wgs84_geografico(self, gdf_points_wgs84: gpd.GeoDataFrame) -> None:
        crs, warnings = _extract_crs(gdf_points_wgs84)
        assert crs is not None
        assert crs.authority == "EPSG"
        assert crs.code == "4326"
        assert crs.is_geographic is True
        assert crs.is_projected is False
        assert warnings == []

    def test_sem_crs_gera_warning(self, gdf_no_crs: gpd.GeoDataFrame) -> None:
        crs, warnings = _extract_crs(gdf_no_crs)
        assert crs is None
        assert len(warnings) == 1
        assert "[WARN]" in warnings[0]
        assert "CRS" in warnings[0]


# ---------------------------------------------------------------------------
# Extracao de geometria
# ---------------------------------------------------------------------------


class TestExtractGeometryInfo:
    def test_homogenea_poligono(self, gdf_polygons_sirgas: gpd.GeoDataFrame) -> None:
        info, warnings = _extract_geometry_info(gdf_polygons_sirgas)
        assert info.geometry_type is OGCGeometryType.POLYGON
        assert info.is_mixed is False
        assert info.types_distribution == {}
        assert info.has_z is False
        assert warnings == []

    def test_multipoligono_mapeado(
        self, gdf_multipolygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        info, _ = _extract_geometry_info(gdf_multipolygons_sirgas)
        assert info.geometry_type is OGCGeometryType.MULTIPOLYGON

    def test_camada_heterogenea(self, gdf_mixed_types: gpd.GeoDataFrame) -> None:
        info, warnings = _extract_geometry_info(gdf_mixed_types)
        assert info.is_mixed is True
        assert info.geometry_type is OGCGeometryType.MIXED
        assert set(info.types_distribution.keys()) == {"Point", "LineString", "Polygon"}
        assert any("heterogenea" in w for w in warnings)

    def test_todas_nulas(self) -> None:
        gdf = gpd.GeoDataFrame(
            {"id": [1, 2]}, geometry=[None, None], crs="EPSG:4326"
        )
        info, warnings = _extract_geometry_info(gdf)
        assert info.geometry_type is OGCGeometryType.UNKNOWN
        assert any("nao-nulas" in w for w in warnings)


# ---------------------------------------------------------------------------
# Contagens de feicoes e topologia
# ---------------------------------------------------------------------------


class TestFeaturesAndTopology:
    def test_features_saudaveis(self, gdf_polygons_sirgas: gpd.GeoDataFrame) -> None:
        info = _extract_features_info(gdf_polygons_sirgas)
        assert info.total_count == 3
        assert info.empty_count == 0
        assert info.invalid_count == 0

    def test_conta_nula_e_vazia_como_empty(
        self, gdf_with_empty_and_null: gpd.GeoDataFrame
    ) -> None:
        info = _extract_features_info(gdf_with_empty_and_null)
        assert info.total_count == 4
        assert info.empty_count == 2  # 1 None + 1 POLYGON EMPTY
        assert info.invalid_count == 0

    def test_detecta_geometria_invalida(
        self, gdf_with_invalid: gpd.GeoDataFrame
    ) -> None:
        info = _extract_features_info(gdf_with_invalid)
        assert info.total_count == 2
        assert info.invalid_count == 1

    def test_topology_com_warning_de_invalido(
        self, gdf_with_invalid: gpd.GeoDataFrame
    ) -> None:
        topo, warnings = _extract_topology(gdf_with_invalid, compute_duplicates=False)
        assert topo.invalid_geometries == 1
        assert any("invalida(s)" in w for w in warnings)

    def test_topology_detecta_duplicatas_quando_habilitado(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        # Duplica a primeira geometria
        dup = gdf_polygons_sirgas.copy()
        dup = gpd.pd.concat([dup, dup.iloc[[0]]], ignore_index=True)
        topo, warnings = _extract_topology(dup, compute_duplicates=True)
        assert topo.duplicate_features >= 1
        assert any("duplicadas" in w for w in warnings)

    def test_topology_ignora_duplicatas_por_default(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        topo, _ = _extract_topology(gdf_polygons_sirgas, compute_duplicates=False)
        assert topo.duplicate_features == 0


# ---------------------------------------------------------------------------
# Extracao de atributos
# ---------------------------------------------------------------------------


class TestExtractAttributes:
    def test_ignora_coluna_geometry(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        schema = _extract_attributes(gdf_polygons_sirgas, sample_size=5)
        field_names = {f.name for f in schema.fields}
        assert "geometry" not in field_names
        assert field_names == {"id_talhao", "especie", "area_ha"}

    def test_field_count(self, gdf_polygons_sirgas: gpd.GeoDataFrame) -> None:
        schema = _extract_attributes(gdf_polygons_sirgas, sample_size=5)
        assert schema.field_count == 3

    def test_calcula_cardinalidade(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        schema = _extract_attributes(gdf_polygons_sirgas, sample_size=5)
        by_name = {f.name: f for f in schema.fields}
        assert by_name["id_talhao"].unique_count == 3
        assert by_name["especie"].unique_count == 2

    def test_sample_size_respeitado(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        schema = _extract_attributes(gdf_polygons_sirgas, sample_size=2)
        for f in schema.fields:
            assert len(f.sample_values) <= 2


# ---------------------------------------------------------------------------
# Extracao de bounds
# ---------------------------------------------------------------------------


class TestExtractBounds:
    def test_bounds_de_poligonos(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        bbox = _extract_bounds(gdf_polygons_sirgas)
        assert bbox is not None
        assert bbox.minx == 200_000.0
        assert bbox.maxx == 205_000.0
        assert bbox.height == 1_000.0

    def test_bounds_nulo_quando_sem_geometria(self) -> None:
        gdf = gpd.GeoDataFrame(
            {"id": [1, 2]}, geometry=[None, None], crs="EPSG:4326"
        )
        assert _extract_bounds(gdf) is None


# ---------------------------------------------------------------------------
# Analise fim-a-fim (nivel unitario, em memoria)
# ---------------------------------------------------------------------------


class TestAnalyzeDataframe:
    def test_diagnostico_saudavel(self, gdf_polygons_sirgas: gpd.GeoDataFrame) -> None:
        diag = _profile(gdf_polygons_sirgas)
        assert diag.kind == "vector"
        assert diag.profiler == PROFILER_NAME
        assert diag.profiler_version == PROFILER_VERSION
        assert diag.features.total_count == 3
        assert diag.geometry.geometry_type is OGCGeometryType.POLYGON
        assert diag.bounds is not None
        assert diag.quality_warnings == []

    def test_diagnostico_acumula_warnings(
        self, gdf_no_crs: gpd.GeoDataFrame
    ) -> None:
        diag = _profile(gdf_no_crs)
        assert diag.crs is None
        assert any("CRS" in w for w in diag.quality_warnings)

    def test_diagnostico_camada_heterogenea(
        self, gdf_mixed_types: gpd.GeoDataFrame
    ) -> None:
        diag = _profile(gdf_mixed_types)
        assert diag.geometry.is_mixed is True
        assert diag.geometry.geometry_type is OGCGeometryType.MIXED

    def test_diagnostico_com_invalido(
        self, gdf_with_invalid: gpd.GeoDataFrame
    ) -> None:
        diag = _profile(gdf_with_invalid)
        assert diag.features.invalid_count == 1
        assert diag.topology.invalid_geometries == 1

    def test_desliga_topologia_via_config(
        self, gdf_with_invalid: gpd.GeoDataFrame
    ) -> None:
        cfg = VectorProfilerConfig(compute_topology=False)
        profiler = VectorProfiler(cfg)
        diag = profiler.analyze_dataframe(
            gdf_with_invalid,
            file_name="x.geojson",
            file_size_bytes=100,
            driver="in-memory",
            file_format=VectorFileFormat.GEOJSON,
        )
        # Topology desligada = valores default do TopologyInfo
        assert diag.topology.invalid_geometries == 0
        assert diag.topology.empty_geometries == 0


# ---------------------------------------------------------------------------
# Integracao: profile(path)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProfileFromDisk:
    def test_profile_shapefile(self, shp_polygons_sirgas_path: Path) -> None:
        diag = profile_vector_file(shp_polygons_sirgas_path)
        assert diag.file_format is VectorFileFormat.SHAPEFILE
        assert diag.file_name == "talhoes.shp"
        assert diag.file_size_bytes > 0
        assert diag.features.total_count == 3
        assert diag.crs is not None
        assert diag.crs.urn == "EPSG:31983"
        assert diag.driver in {"ESRI Shapefile", "SHP"}

    def test_profile_geojson(self, geojson_points_wgs84_path: Path) -> None:
        diag = profile_vector_file(geojson_points_wgs84_path)
        assert diag.file_format is VectorFileFormat.GEOJSON
        assert diag.geometry.geometry_type is OGCGeometryType.POINT
        assert diag.crs is not None
        assert diag.crs.urn == "EPSG:4326"

    def test_profile_geopackage(self, gpkg_polygons_sirgas_path: Path) -> None:
        diag = profile_vector_file(gpkg_polygons_sirgas_path)
        assert diag.file_format is VectorFileFormat.GEOPACKAGE
        assert diag.features.total_count == 3

    def test_arquivo_inexistente_levanta_filenotfound(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            profile_vector_file(tmp_path / "inexistente.shp")

    def test_extensao_desconhecida_levanta(self, tmp_path: Path) -> None:
        p = tmp_path / "dados.xyz"
        p.write_text("nada")
        with pytest.raises(UnsupportedFormatError):
            profile_vector_file(p)


# ---------------------------------------------------------------------------
# Round-trip: JSON do diagnostico continua valido
# ---------------------------------------------------------------------------


class TestJSONRoundTrip:
    def test_diagnostico_do_profiler_e_serializavel(
        self, gdf_polygons_sirgas: gpd.GeoDataFrame
    ) -> None:
        diag = _profile(gdf_polygons_sirgas)
        as_json = diag.model_dump_json()
        reconstructed = VectorDiagnostic.model_validate_json(as_json)
        assert reconstructed == diag