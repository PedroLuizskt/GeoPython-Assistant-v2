# Especificacao do Schema de Diagnostico Geoespacial

**Modulo:** `geopyassistant.diagnostics.schema`
**Versao corrente do schema:** `0.2.0` (constante `DIAGNOSTIC_SCHEMA_VERSION`)
**Status:** Estavel para uso interno; sujeito a versionamento SemVer.

---

## 1. Proposito

Este documento especifica o contrato estruturado utilizado para descrever um arquivo geoespacial (vetorial ou matricial) no GeoPython Assistant v2. O contrato e implementado em Pydantic v2 e atua como interface entre a camada de *profiling* (que le o arquivo) e a camada de *generation* (que produz a resposta do LLM).

A motivacao para um contrato formal, em vez de um dicionario solto, e tripla. Primeiro, **garantia de invariantes geoespaciais em runtime** (por exemplo, `minx <= maxx`, codigo EPSG numerico, `min <= mean <= max` em estatisticas) que falham cedo e com mensagem clara. Segundo, **reprodutibilidade cientifica**, via metadados de proveniencia obrigatorios. Terceiro, **interoperabilidade**, ja que o schema JSON exportavel via `model_json_schema()` permite uso em outras linguagens, em validacao de payloads de API e em geracao de documentacao automatica.

## 2. Visao geral

O sistema produz um unico tipo polimorfico de topo, `GeospatialDiagnostic`, definido como uma **uniao discriminada** com Pydantic:

```python
GeospatialDiagnostic = Annotated[
    VectorDiagnostic | RasterDiagnostic,
    Field(discriminator="kind"),
]
```

O campo `kind: Literal["vector", "raster"]` atua como tag discriminadora. Em runtime, Pydantic seleciona a variante correta com base nesse campo, viabilizando despacho polimorfico sem `isinstance` em chamadas comuns.

Cada variante herda de `_DiagnosticBase`, que contem campos comuns: proveniencia (`diagnostic_version`, `generated_at`, `profiler`, `profiler_version`), identidade do arquivo (`file_name`, `file_size_bytes`, `driver`), CRS opcional e lista de avisos de qualidade.

## 3. Modelos comuns

### 3.1 `BoundingBox`

Envoltoria retangular *axis-aligned* no sistema de referencia do dataset. Coordenadas seguem a ordem cartografica `(X = leste, Y = norte)` em todas as situacoes, independentemente da ordem de eixos do CRS, alinhando-se com a convencao adotada por GeoPandas em `total_bounds`.

| Campo  | Tipo  | Restricao                |
|--------|-------|--------------------------|
| `minx` | float | `minx <= maxx`           |
| `miny` | float | `miny <= maxy`           |
| `maxx` | float |                          |
| `maxy` | float |                          |

Propriedades derivadas: `width = maxx - minx`, `height = maxy - miny`. Caixas degeneradas (largura ou altura zero) sao aceitas para representar feicoes pontuais.

### 3.2 `CRSInfo`

Sistema de Referencia de Coordenadas, modelado em granularidade compativel com `pyproj.CRS`. Quando o arquivo nao declara CRS, o campo `crs` do diagnostico deve ser `None`, em vez de um `CRSInfo` preenchido parcialmente; essa decisao preserva a semantica de "CRS desconhecido" empregada pela maioria das bibliotecas geoespaciais.

Invariantes garantidas:

- `authority` e `code` devem ser ambos presentes ou ambos ausentes;
- quando `authority == "EPSG"`, o `code` deve ser numerico;
- `is_projected` e `is_geographic` sao mutuamente exclusivos.

A propriedade `urn` retorna a forma compacta `"EPSG:4326"`, util em logs e citacoes em prompts.

## 4. Modelos vetoriais

### 4.1 `GeometryInfo`

Caracterizacao geometrica da camada vetorial. O campo `geometry_type` usa o enum `OGCGeometryType`, baseado em OGC Simple Features. Camadas heterogeneas devem ser marcadas com `is_mixed=True`, e a distribuicao deve ser informada em `types_distribution: dict[str, int]`. Coordenadas Z (3D) e M (medida) sao expressas por flags booleanas, seguindo a pratica de Shapely 2 e GDAL 3.

### 4.2 `FeatureInfo`

Tres contagens: `total_count`, `empty_count` (feicoes sem geometria), `invalid_count` (geometrias topologicamente invalidas). A invariante semantica `empty + invalid <= total` e verificada em runtime.

### 4.3 `AttributeField` e `AttributeSchema`

A tabela de atributos e modelada como uma lista ordenada de `AttributeField`, preservando a ordem declarada no arquivo. Cada campo carrega nome, dtype, contagens de nulos e cardinalidade, e ate cinco amostras textualizadas (`sample_values`) para fornecer contexto ao LLM sem inflacionar o prompt.

### 4.4 `TopologyInfo`

Indicadores de qualidade topologica: `invalid_geometries`, `empty_geometries`, `duplicate_features`. A deteccao de duplicatas e opcional (e custosa para camadas grandes); o profiler decide quando computa-la.

## 5. Modelos matriciais

### 5.1 `RasterSpatialInfo`

Caracterizacao espacial do raster. O campo `transform` carrega os seis coeficientes da transformacao afim no formato GDAL (`[a, b, c, d, e, f]`), que mapeia coordenadas de pixel `(col, row)` em coordenadas mundo `(x, y)` no CRS nativo. Resolucoes sao reportadas em valores absolutos.

### 5.2 `BandStatistics`

Estatisticas descritivas calculadas sobre pixels validos. A invariante `min <= mean <= max` e verificada em runtime, prevenindo silenciamento de bugs comuns em *profilers* (mascara de nodata aplicada errado, *overflow* em soma).

### 5.3 `BandInfo`

Descritor de uma banda individual, 1-indexado conforme rasterio e GDAL. Carrega `dtype`, `nodata`, `description`, `statistics` opcionais, `color_interpretation` (enum) e flags para bandas categoricas. Quando `is_categorical=True`, o campo `categories` deve listar os valores discretos observados.

## 6. Versionamento

O schema segue **Semantic Versioning** estritamente:

- **MAJOR**: quebra de contrato (renomeacao ou remocao de campo, mudanca de tipo, alteracao de invariante).
- **MINOR**: adicao de campo opcional ou novo enum value.
- **PATCH**: correcao de bug ou de docstring sem efeito de tipo.

Toda mudanca exige atualizacao da constante `DIAGNOSTIC_SCHEMA_VERSION` e justificativa no `CHANGELOG`. Diagnosticos persistidos em disco (cache do Chroma, por exemplo) devem ser recomputados quando a versao MAJOR muda.

## 7. Exemplo de payload vetorial

```json
{
  "diagnostic_version": "0.2.0",
  "generated_at": "2026-06-29T22:00:00Z",
  "profiler": "vector_profiler",
  "profiler_version": "0.2.0",
  "file_name": "talhoes_eucalipto.shp",
  "file_size_bytes": 1524300,
  "driver": "ESRI Shapefile",
  "crs": {
    "authority": "EPSG",
    "code": "31983",
    "name": "SIRGAS 2000 / UTM zone 23S",
    "is_projected": true,
    "is_geographic": false,
    "units": "metre",
    "axis_order": "easting,northing"
  },
  "kind": "vector",
  "file_format": "shapefile",
  "geometry": {
    "geometry_type": "Polygon",
    "is_mixed": false,
    "has_z": false,
    "has_m": false
  },
  "features": {"total_count": 312, "empty_count": 0, "invalid_count": 2},
  "attributes": {
    "fields": [
      {"name": "id_talhao", "dtype": "int64", "unique_count": 312}
    ]
  },
  "bounds": {"minx": 200000.0, "miny": 7500000.0, "maxx": 250000.0, "maxy": 7600000.0},
  "quality_warnings": []
}
```

## 8. Referencias

- Open Geospatial Consortium. *OpenGIS Implementation Specification for Geographic information - Simple feature access - Part 1: Common architecture*. OGC 06-103r4, 2011.
- International Organization for Standardization. *ISO 19111:2019 - Geographic information - Referencing by coordinates*. Geneva, 2019.
- Pydantic Documentation. *Discriminated Unions*. https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions
- GDAL Project. *Raster Data Model*. https://gdal.org/user/raster_data_model.html
- Gillies, S. *Shapely User Manual*. https://shapely.readthedocs.io
