"""
Configuracao global do pytest e fixtures compartilhadas.

Este modulo concentra fixtures utilizadas por varios testes, principalmente
GeoDataFrames construidos em memoria com Shapely, para evitar dependencia de
arquivos externos e manter a suite rapida (< 1 s por teste).

Fixtures baseadas em arquivo usam `tmp_path` do pytest, criando arquivos
efemeros que sao coletados automaticamente ao final de cada teste.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import (
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)

# ---------------------------------------------------------------------------
# CRS de referencia
# ---------------------------------------------------------------------------

EPSG_WGS84 = 4326
EPSG_SIRGAS_UTM23S = 31983


# ---------------------------------------------------------------------------
# GeoDataFrames em memoria
# ---------------------------------------------------------------------------


@pytest.fixture
def gdf_polygons_sirgas() -> gpd.GeoDataFrame:
    """
    Camada homogenea de tres poligonos em SIRGAS 2000 / UTM 23S.

    Representa um cenario tipico de talhoes florestais no sudeste brasileiro.
    """
    geoms = [
        Polygon([(200_000, 7_500_000), (201_000, 7_500_000),
                 (201_000, 7_501_000), (200_000, 7_501_000)]),
        Polygon([(202_000, 7_500_000), (203_000, 7_500_000),
                 (203_000, 7_501_000), (202_000, 7_501_000)]),
        Polygon([(204_000, 7_500_000), (205_000, 7_500_000),
                 (205_000, 7_501_000), (204_000, 7_501_000)]),
    ]
    return gpd.GeoDataFrame(
        {
            "id_talhao": [1, 2, 3],
            "especie": [
                "Eucalyptus urograndis",
                "Eucalyptus urograndis",
                "Pinus elliottii",
            ],
            "area_ha": [100.0, 100.0, 100.0],
        },
        geometry=geoms,
        crs=f"EPSG:{EPSG_SIRGAS_UTM23S}",
    )


@pytest.fixture
def gdf_points_wgs84() -> gpd.GeoDataFrame:
    """Camada de pontos em WGS 84 (parcelas de inventario)."""
    geoms = [Point(-45.0, -21.0), Point(-45.1, -21.1), Point(-45.2, -21.2)]
    return gpd.GeoDataFrame(
        {"parcela": ["P01", "P02", "P03"], "dap_medio": [18.2, 22.1, 19.7]},
        geometry=geoms,
        crs=f"EPSG:{EPSG_WGS84}",
    )


@pytest.fixture
def gdf_no_crs() -> gpd.GeoDataFrame:
    """Camada sem CRS declarado (caso patologico)."""
    geoms = [Point(0, 0), Point(1, 1)]
    return gpd.GeoDataFrame({"id": [1, 2]}, geometry=geoms, crs=None)


@pytest.fixture
def gdf_mixed_types() -> gpd.GeoDataFrame:
    """Camada heterogenea com tres tipos geometricos distintos."""
    geoms = [
        Point(0, 0),
        LineString([(0, 0), (1, 1)]),
        Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
    ]
    return gpd.GeoDataFrame(
        {"kind": ["ponto", "linha", "poligono"]},
        geometry=geoms,
        crs=f"EPSG:{EPSG_WGS84}",
    )


@pytest.fixture
def gdf_with_invalid() -> gpd.GeoDataFrame:
    """
    Camada com uma geometria invalida (bowtie: quadrilatero auto-intersectante).

    Bowtie e o exemplo classico de geometria topologicamente invalida:
    dois triangulos que se tocam apenas no vertice central.
    """
    valid = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    bowtie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0)])
    return gpd.GeoDataFrame(
        {"nome": ["valido", "invalido"]},
        geometry=[valid, bowtie],
        crs=f"EPSG:{EPSG_WGS84}",
    )


@pytest.fixture
def gdf_with_empty_and_null() -> gpd.GeoDataFrame:
    """Camada mesclando geometrias validas, nula e vazia."""
    geoms = [
        Point(0, 0),
        None,
        Polygon(),  # POLYGON EMPTY
        Point(1, 1),
    ]
    return gpd.GeoDataFrame(
        {"tag": ["ok", "nula", "vazia", "ok"]},
        geometry=geoms,
        crs=f"EPSG:{EPSG_WGS84}",
    )


@pytest.fixture
def gdf_multipolygons_sirgas() -> gpd.GeoDataFrame:
    """Camada de multipoligonos, util para verificar mapeamento OGC."""
    mp1 = MultiPolygon(
        [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
        ]
    )
    return gpd.GeoDataFrame(
        {"id": [1]}, geometry=[mp1], crs=f"EPSG:{EPSG_SIRGAS_UTM23S}"
    )


# ---------------------------------------------------------------------------
# Fixtures que exigem arquivo em disco (para testar o loop I/O completo)
# ---------------------------------------------------------------------------


@pytest.fixture
def shp_polygons_sirgas_path(
    tmp_path: Path, gdf_polygons_sirgas: gpd.GeoDataFrame
) -> Path:
    """Grava a camada de poligonos em SHP efemero e retorna o caminho."""
    out = tmp_path / "talhoes.shp"
    gdf_polygons_sirgas.to_file(out, driver="ESRI Shapefile")
    return out


@pytest.fixture
def geojson_points_wgs84_path(
    tmp_path: Path, gdf_points_wgs84: gpd.GeoDataFrame
) -> Path:
    """Grava a camada de pontos em GeoJSON efemero e retorna o caminho."""
    out = tmp_path / "parcelas.geojson"
    gdf_points_wgs84.to_file(out, driver="GeoJSON")
    return out


@pytest.fixture
def gpkg_polygons_sirgas_path(
    tmp_path: Path, gdf_polygons_sirgas: gpd.GeoDataFrame
) -> Path:
    """Grava a camada em GeoPackage efemero e retorna o caminho."""
    out = tmp_path / "talhoes.gpkg"
    gdf_polygons_sirgas.to_file(out, driver="GPKG")
    return out