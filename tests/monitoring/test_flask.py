import sys
import pytest
import runpy
from unittest.mock import patch, MagicMock
from monitoring import main, create_app
@pytest.fixture
def mock_flask_app():
    #Fixture to mock Flask app creation and running
    mock_app = MagicMock()
    mock_app.run = MagicMock()
    return mock_app

@pytest.fixture
def valid_config(provide_dummy_config):
    #Fixture providing valid config with host/port
    cfg = provide_dummy_config
    cfg.host = "127.0.0.1"
    cfg.port = "5000"
    return cfg

def test_main_with_valid_config(valid_config, mock_flask_app):
    with patch('monitoring.validate_config', return_value=valid_config) as mock_validate, \
         patch('monitoring.create_app', return_value=mock_flask_app):
        
        main()  # Directly call the main function
        
        mock_validate.assert_called_once_with(strict=False, api=True)
        mock_flask_app.run.assert_called_once_with(
            host="127.0.0.1",
            port="5000"
        )

def test_main_with_missing_host_port(provide_dummy_config, mock_flask_app):
    # Update config with empty host/port
    provide_dummy_config.host = ""
    provide_dummy_config.port = ""
    
    with patch('monitoring.validate_config', return_value=provide_dummy_config), \
         patch('monitoring.create_app', return_value=mock_flask_app):
        
        main()
        
        mock_flask_app.run.assert_called_once_with(host=None, port=None)

def test_main_config_validation_failure(mock_flask_app):
    with patch('monitoring.validate_config', side_effect=ValueError("Invalid config")), \
         patch('monitoring.create_app', return_value=mock_flask_app):
        
        with pytest.raises(ValueError, match="Invalid config"):
            main()

def test_main_app_creation_failure(valid_config):
    with patch('monitoring.validate_config', return_value=valid_config), \
         patch('monitoring.create_app', side_effect=RuntimeError("App creation failed")):
        
        with pytest.raises(RuntimeError, match="App creation failed"):
            main()

def test_main_app_run_failure(valid_config, mock_flask_app):
    mock_flask_app.run.side_effect = OSError("Port in use")
    
    with patch('monitoring.validate_config', return_value=valid_config), \
         patch('monitoring.create_app', return_value=mock_flask_app):
        
        with pytest.raises(OSError, match="Port in use"):
            main()