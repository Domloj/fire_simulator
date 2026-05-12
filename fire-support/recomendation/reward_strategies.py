from dataclasses import dataclass
from typing import List
from enum import Enum

@dataclass
class RewardConfigConservative:
    LOST_SECTOR_PENALTY = 200 
    EXTINGUISHED_FIRES_REWARD = 50
    SPREAD_PREVENTION_REWARD = 100
    BURNED_SECTOR_PENALTY = 150
    SECTOR_FIRE_LEVEL_PENALTY = 20
    name = "conservative"

@dataclass
class RewardConfigAggressive:
    LOST_SECTOR_PENALTY = 0
    EXTINGUISHED_FIRES_REWARD = 0
    SPREAD_PREVENTION_REWARD = 0
    BURNED_SECTOR_PENALTY = 0
    SECTOR_FIRE_LEVEL_PENALTY = 1000
    name = "aggressive"

@dataclass
class RewardConfigBalanced:
    LOST_SECTOR_PENALTY = 50
    EXTINGUISHED_FIRES_REWARD = 100
    SPREAD_PREVENTION_REWARD = 50
    BURNED_SECTOR_PENALTY = 100
    SECTOR_FIRE_LEVEL_PENALTY = 50
    name = "balanced"

REWARD_CONFIGS = {
    "balanced": RewardConfigBalanced(),
    "aggressive": RewardConfigAggressive(),
    "conservative": RewardConfigConservative(),
}

def get_config_by_name(name: str):
    if name in REWARD_CONFIGS:
        return REWARD_CONFIGS[name]
    else:
        return RewardConfigBalanced()
