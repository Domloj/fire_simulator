
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import support_service
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from support_service import SupportService
from llm.config import LLMConfig

class TestLLMMode(unittest.TestCase):
    def setUp(self):
        # Mock LLM Config to force LLM mode
        self.mock_config = LLMConfig(
            recommendation_mode="llm",
            llm_api_key="sk-test-key",
            enable_llm_coordination=True
        )
        
    @patch('support_service.MCTSWorkerPool')
    @patch('support_service.LLMClient')
    def test_llm_mode_skips_mcts(self, MockLLMClient, MockWorkerPool):
        # Initialize service with our config
        service = SupportService(llm_config=self.mock_config)
        
        # Mock dependencies
        service.state_manager = MagicMock()
        service.state_manager.get_state_copy.return_value = ({}, [{"id": 1}], []) # sectors, brigades, patrols
        service.state_manager.get_config.return_value = {"some": "config"}
        service.rabbitmq = MagicMock()
        
        # Mock internal methods to isolate logic
        service._convert_recommendations = MagicMock(return_value=[])
        service._generate_llm_recommendations = MagicMock(return_value=[
            {"unitId": 1, "sectorId": 1, "unitType": "fireBrigade"}
        ])
        service._coordinate_with_agents = MagicMock(side_effect=lambda x, y: x)
        service._filter_travelling_units = MagicMock(side_effect=lambda x, y: x)
        service._update_travelling_units = MagicMock()
        service._recommendations_are_similar = MagicMock(return_value=False)
        
        # Mock state data
        mock_forest_map = MagicMock()
        mock_forest_map.fireBrigades = [MagicMock(), MagicMock()] # 2 brigades
        mock_forest_map.sectors = [[MagicMock()]]
        
        with patch('support_service.StateConverter.state_to_forest_map', return_value=mock_forest_map):
            # Trigger recommendation generation
            service._generate_recommendations()
            
            # VERIFICATION 1: MCTS submit_task should NOT be called
            service.worker_pool.submit_task.assert_not_called()
            
            # VERIFICATION 2: _generate_llm_recommendations should be called with force_all=True
            service._generate_llm_recommendations.assert_called_with(
                mock_forest_map, 
                min_recommendations=2, 
                force_all=True
            )
            
            # VERIFICATION 3: Recommendations were published
            service.rabbitmq.publish_recommendation.assert_called()

    def test_llm_env_disabled(self):
        # Ensure the LLM_ENABLED env var disables LLM globally
        os.environ['LLM_ENABLED'] = 'false'
        cfg = LLMConfig()
        self.assertFalse(cfg.is_llm_enabled)
        del os.environ['LLM_ENABLED']

if __name__ == '__main__':
    unittest.main()
