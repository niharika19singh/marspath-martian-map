from backend.app.services.data_catalog import DataCatalogService


def test_layer_availability_semantics():
    service = DataCatalogService()
    response = service.get_layer_list()

    layers_by_id = {lyr.id: lyr for lyr in response.layers}

    # Visual Basemap must be directly renderable
    basemap = layers_by_id["mars_trek_imagery_basemap"]
    assert basemap.is_renderable is True
    assert basemap.layer_type == "tile_service"
    assert basemap.render_url is not None
    assert "https://trek.nasa.gov" in basemap.render_url

    # Elevation, Slope, Roughness, Hazard are analysis matrices, NOT renderable tile layers
    for layer_id in [
        "mars_elevation_jezero",
        "mars_slope_degrees",
        "mars_roughness_tri",
        "mars_traversability_mask",
    ]:
        layer = layers_by_id[layer_id]
        assert layer.is_renderable is False
        assert layer.layer_type == "analysis_derived"
        assert layer.render_url is None
        assert "Internal analysis layer" in layer.description
