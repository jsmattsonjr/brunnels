import unittest
from unittest.mock import patch, MagicMock, call

from src.brunnels.config import BrunnelsConfig
from src.brunnels.route import Route
# Brunnel import might not be strictly needed if brunnels list is empty and no methods are called
# from src.brunnels.brunnel import Brunnel
from src.brunnels.visualization import create_route_map

class TestCreateRouteMapLayerControl(unittest.TestCase):

    @patch('src.brunnels.visualization.folium.LayerControl')
    @patch('src.brunnels.visualization.folium.TileLayer')
    @patch('src.brunnels.visualization.folium.Map')
    @patch('src.brunnels.visualization.BrunnelLegend') # Mock for BrunnelLegend
    @patch('src.brunnels.visualization.folium.PolyLine')  # Mock for PolyLine
    @patch('src.brunnels.visualization.folium.Marker')    # Mock for Marker
    def test_create_route_map_adds_tile_layers_and_layer_control(
        self,
        mock_folium_marker,
        mock_folium_polyline,
        mock_brunnel_legend,
        mock_folium_map,
        mock_folium_tilelayer,
        mock_folium_layercontrol
    ):
        mock_route = MagicMock(spec=Route)
        # Configure mock_route with minimal necessary attributes/methods
        mock_route.__len__.return_value = 2 # Needs at least two points for start/end markers
        mock_route.__getitem__.side_effect = lambda x: MagicMock(latitude=0, longitude=0) # Return a mock point for any index
        mock_route.get_bbox.return_value = (0.0, 0.0, 1.0, 1.0) # south, west, north, east
        mock_route.get_visualization_coordinates.return_value = [(0.0,0.0), (1.0,1.0)] # For route PolyLine

        # Mock the map instance returned by folium.Map()
        mock_map_instance = MagicMock(name="map_instance")
        mock_folium_map.return_value = mock_map_instance

        # Mock instances returned by TileLayer and LayerControl constructors
        mock_tilelayer_standard_instance = MagicMock(name="tilelayer_standard_instance")
        mock_tilelayer_satellite_instance = MagicMock(name="tilelayer_satellite_instance")
        mock_layercontrol_instance = MagicMock(name="layercontrol_instance")

        # Configure side_effect for TileLayer to return specific mocks in order
        mock_folium_tilelayer.side_effect = [
            mock_tilelayer_standard_instance,
            mock_tilelayer_satellite_instance
        ]
        mock_folium_layercontrol.return_value = mock_layercontrol_instance

        brunnels = []

        config = BrunnelsConfig()
        config.bbox_buffer = 10.0
        config.metrics = False
        # Default log_level="INFO" is fine for this test

        create_route_map(
            route=mock_route,
            output_filename="test_map_layers.html",
            brunnels=brunnels,
            config=config
        )

        mock_folium_map.assert_called_once()
        _, map_kwargs = mock_folium_map.call_args
        # The 'tiles' argument to folium.Map was removed in visualization.py, default is now None (then TileLayers are added)
        # Check that it was called with location and tiles=None
        self.assertEqual(map_kwargs.get('tiles'), None)

        self.assertEqual(mock_folium_tilelayer.call_count, 2)

        tile_layer_calls = mock_folium_tilelayer.call_args_list

        standard_call_kwargs = tile_layer_calls[0][1] # kwargs of the first call
        self.assertEqual(standard_call_kwargs.get('tiles'), "CartoDB positron")
        self.assertEqual(standard_call_kwargs.get('name'), "Standard")
        self.assertTrue(standard_call_kwargs.get('control'))
        self.assertIn('CARTO', standard_call_kwargs.get('attr', '')) # Changed 'CartoDB' to 'CARTO'

        satellite_call_kwargs = tile_layer_calls[1][1] # kwargs of the second call
        self.assertEqual(satellite_call_kwargs.get('tiles'), "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")
        self.assertEqual(satellite_call_kwargs.get('name'), "Satellite")
        self.assertTrue(satellite_call_kwargs.get('control'))
        self.assertIn("Tiles &copy; Esri", satellite_call_kwargs.get('attr', ''))

        mock_tilelayer_standard_instance.add_to.assert_called_once_with(mock_map_instance)
        mock_tilelayer_satellite_instance.add_to.assert_called_once_with(mock_map_instance)

        mock_folium_layercontrol.assert_called_once_with()
        mock_layercontrol_instance.add_to.assert_called_once_with(mock_map_instance)

        # Check that other map elements are still added
        mock_folium_polyline.assert_called() # Route polyline
        self.assertEqual(mock_folium_marker.call_count, 2) # Start and End markers
        mock_brunnel_legend.assert_called() # Legend

if __name__ == '__main__':
    unittest.main()
