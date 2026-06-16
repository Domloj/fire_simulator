export type RecommendedAction = {
    unitId: number;
    sectorId: number;
  };
  
export type Recommendation = {
  timestamp: number;
  recommendedActions: RecommendedAction[];
  priority: string;
};


