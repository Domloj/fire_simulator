#!/usr/bin/env python3
"""
Test script for MCTS recommendations
Provide simulation state (sectors + fire brigades) and get recommendations
"""

import json
import sys
import logging
from typing import Dict, List, Tuple
from pathlib import Path

from logger.logging_config import setup_logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.forest_map import ForestMap
from simulation.sectors.fire_state import FireState
from simulation.agent_state import AGENT_STATE
from simulation.location import Location
from recomendation.mcts_test import predict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def state_to_forest_map(sectors: Dict[int, Dict], fire_brigades: Dict[str, Dict], config: Dict) -> ForestMap:
    """
    Convert simulation state to ForestMap
    
    Args:
        sectors: Dict of sector_id -> sector state
        fire_brigades: Dict of brigade_id -> brigade state
        config: Forest configuration
    
    Returns:
        ForestMap instance
    """
    # Create base forest map from config
    forest_map = ForestMap.from_conf(config)
    
    # Update sectors with current state
    for row in forest_map.sectors:
        for sector in row:
            if sector and sector.sector_id in sectors:
                sector_state = sectors[sector.sector_id]
                
                # Update fire levels
                sector.fire_level = sector_state.get('state', {}).get('fireLevel', 0)
                sector.burn_level = sector_state.get('state', {}).get('burnLevel', 0)
                sector.extinguish_level = sector_state.get('state', {}).get('extinguishLevel', 0)
                
                # Update fire state
                if sector.fire_level > 0:
                    sector._fire_state = FireState.ACTIVE
                else:
                    sector._fire_state = FireState.INACTIVE
    
    # Update fire brigades with current state
    brigade_id_map = {str(b.fire_brigade_id): b for b in forest_map.fireBrigades}
    
    for brigade_state in fire_brigades.values():
        brigade_id_str = str(brigade_state.get('fireBrigadeId') or brigade_state.get('fire_brigade_id'))
        if brigade_id_str in brigade_id_map:
            brigade = brigade_id_map[brigade_id_str]
            
            location_data = brigade_state.get('currentLocation') or brigade_state.get('location', {})
            if location_data:
                brigade._location = Location(
                    latitude=location_data.get('latitude', 0),
                    longitude=location_data.get('longitude', 0)
                )
            
            state_name = brigade_state.get('state', 'AVAILABLE')
            state_mapping = {
                'AVAILABLE': AGENT_STATE.AVAILABLE,
                'TRAVELLING': AGENT_STATE.TRAVELLING,
                'EXTINGUISHING': AGENT_STATE.EXECUTING,
            }
            brigade._state = state_mapping.get(state_name, AGENT_STATE.AVAILABLE)
    
    return forest_map


def test_recommendations(state_file: str = None, config_file: str = None):
    """
    Test MCTS recommendations with provided state
    
    Args:
        state_file: Path to JSON file with simulation state (sectors + fire brigades)
        config_file: Path to JSON file with forest configuration
    """
    
    if state_file:
        with open(state_file, 'r') as f:
            state_data = json.load(f)
    else:
        state_data = load_state_from_file("forest_3x3_test.json")

    if config_file:
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        with open("forest_config_3x3.json", 'r') as f:
            config = json.load(f)
    
    sectors_list = state_data.get('sectors', [])
    fire_brigades_list = state_data.get('fireBrigades', [])
    
    # Convert lists to dicts: sector_id -> sector_state, fire_brigade_id -> brigade_state
    sectors_dict = {sector.get('sectorId'): sector for sector in sectors_list}
    fire_brigades_dict = {brigade.get('fireBrigadeId'): brigade for brigade in fire_brigades_list}
    
    print("=" * 60)
    print("MCTS RECOMMENDATION TEST")
    print("=" * 60)
    print(f"Sectors: {len(sectors_list)}")
    print(f"Fire Brigades: {len(fire_brigades_list)}")
    
    print("\nCurrent Fire Situation:")
    active_fires = 0
    for sector in sectors_list:
        fire_level = sector.get('state', {}).get('fireLevel', 0)
        if fire_level > 0:
            active_fires += 1
            burn_level = sector.get('state', {}).get('burnLevel', 0)
            print(f"  Sector {sector.get('sectorId')}: Fire={fire_level:.1f}, Burn={burn_level:.1f}")
    
    if active_fires == 0:
        print("  No active fires")
        return []
    
    print(f"\nTotal active fires: {active_fires}")
    
    print("\nFire Brigade Status:")
    for brigade in fire_brigades_list:
        state = brigade.get('state', 'UNKNOWN')
        location = brigade.get('location', {}) or brigade.get('currentLocation', {})
        lat = location.get('latitude', 0)
        lon = location.get('longitude', 0)
        print(f"  Brigade {brigade.get('fireBrigadeId', 'UNKNOWN')}: {state} at ({lat:.6f}, {lon:.6f})")
    
    print("\nConverting state to ForestMap...")
    forest_map = state_to_forest_map(sectors_dict, fire_brigades_dict, config)
    
    logger.debug("Running MCTS (this may take a few seconds)...")
    recommendations = predict(forest_map)
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if recommendations:
        print(f"Found {len(recommendations)} recommendations:")
        for agent_idx, sector_id in recommendations:
            brigade = forest_map.fireBrigades[agent_idx]
            brigade_id = brigade.fire_brigade_id
            sector = None
            for row in forest_map.sectors:
                for s in row:
                    if s and s.sector_id == sector_id:
                        sector = s
                        break
            
            if sector:
                print(f"  • Send Brigade {brigade_id} → Sector {sector_id}")
                print(f"      Fire Level: {sector.fire_level:.1f}, Burn Level: {sector.burn_level:.1f}")
            else:
                print(f"  • Send Brigade {brigade_id} → Sector {sector_id}")
        
        # Format as JSON for easy consumption
        print("\nJSON Output:")
        json_recommendations = [
            {
                "unitId": int(forest_map.fireBrigades[agent_idx].fire_brigade_id),
                "sectorId": int(sector_id)
            }
            for agent_idx, sector_id in recommendations
        ]
        print(json.dumps({
            "timestamp": state_data.get('timestamp', 0),
            "recommendedActions": json_recommendations,
            "priority": "HIGH"
        }, indent=2))
    else:
        print("No recommendations generated (no optimal actions found)")
    
    print("=" * 60)
    
    return recommendations

def load_state_from_file(filepath: str):
    """Load simulation state from JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)


def save_recommendations_to_file(recommendations: List[Tuple[int, int]], output_file: str, forest_map: ForestMap):
    """Save recommendations to JSON file"""
    json_recommendations = [
        {
            "unitId": int(forest_map.fireBrigades[agent_idx].fire_brigade_id),
            "sectorId": int(sector_id)
        }
        for agent_idx, sector_id in recommendations
    ]
    
    output = {
        "timestamp": 0,  # Will be set by caller
        "recommendedActions": json_recommendations,
        "priority": "HIGH"
    }
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"Recommendations saved to {output_file}")


if __name__ == '__main__':
    import argparse

    setup_logging('test_recommendations')
    
    parser = argparse.ArgumentParser(description='Test MCTS recommendations')
    parser.add_argument('--state', type=str, help='Path to state JSON file')
    parser.add_argument('--config', type=str, help='Path to config JSON file')
    parser.add_argument('--output', type=str, help='Path to save recommendations JSON')
    
    args = parser.parse_args()
    
    recommendations = test_recommendations(args.state, args.config)
    
    # if args.output and recommendations:
    #     # Need to reload forest_map to save properly
    #     # This is simplified, in real usage you'd pass forest_map through
    #     print(f"\nTo save: python test_recommendations.py --state {args.state} --config {args.config} --output {args.output}")
