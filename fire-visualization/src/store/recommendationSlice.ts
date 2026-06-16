import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type UnitType = 'fireBrigade' | 'foresterPatrol';

interface ActionItem {
  unitId:       string;
  sectorId:     string;
  description:  string;
  unitType?:    UnitType;
  actionType?:  string;
}

interface Recommendation {
  timestamp:  string;
  priority:   string;

  recommendedActions: ActionItem[];
}

interface RecommendationState {
  recommendations:  Record<string, ActionItem>;
  timestamp:        string | null;
  priority:         string | null;
  autoApplyEnabled: boolean;
}

const initialState: RecommendationState = {
  recommendations:  {},
  timestamp:        null,
  priority:         null,
  autoApplyEnabled: false,
};

export const recommendationSlice = createSlice({
  name: 'recommendation',
  initialState,
  reducers: {
    updateRecommendation(state, action: PayloadAction<Recommendation>) {
      const { timestamp, recommendedActions, priority } = action.payload;
      const getKey = ({ unitType, unitId }: { unitType: UnitType; unitId: string }) => unitType ? `${unitType}:${unitId}` : unitId;

      state.recommendations = {};

      for (const item of recommendedActions) {
        state.recommendations[getKey({ unitType: item.unitType || 'fireBrigade', unitId: item.unitId })] = item;
      }

      state.timestamp = timestamp;
      state.priority = priority;
    },
    setAutoApplyEnabled(state, action: PayloadAction<boolean>) {
      state.autoApplyEnabled = action.payload;
    },
  },
});

export const { updateRecommendation, setAutoApplyEnabled } = recommendationSlice.actions;
export default recommendationSlice.reducer;