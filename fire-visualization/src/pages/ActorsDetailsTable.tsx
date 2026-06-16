import { useSelector } from 'react-redux';
import {
    Box,
    Typography,
    Paper,
    Table,
    TableHead,
    TableRow,
    TableCell,
    TableBody,
    TableContainer,
    Button,
    Chip
} from '@mui/material';
import { RootState } from '../store/reduxStore';
import { useMemo, useCallback, useState } from 'react';
import { sendBrigadeOrForesterMoveOrder } from '../store/serverCommunicationReducers';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '../store/reduxStore';
import { MoveAgentModal } from '../components/simulation/MoveAgentModal';

export default function ActorsDetailsTable() {
    const dispatch: AppDispatch = useDispatch();
    const mapConfigState = useSelector((state: RootState) => state.mapConfiguration);
    const recommendations = useSelector((state: RootState) => state.recommendation.recommendations);
    const [moveModalOpen, setMoveModalOpen] = useState(false);
    const [selectedAgent, setSelectedAgent] = useState<{
        id: number;
        type: 'Fire Brigade' | 'Forester Patrol';
        currentSectorId: number;
    } | null>(null);

    const {
        configuration: mapConfiguration,
    } = mapConfigState || {};

    const fireBrigades = mapConfiguration?.fireBrigades || [];
    const foresterPatrols = mapConfiguration?.foresterPatrols || [];
    const sectorIds = useMemo(() => new Set((mapConfiguration?.sectors || []).map((s: any) => s.sectorId)), [mapConfiguration?.sectors]);

    // Combine all agents with their type
    const agents = useMemo(() => {
        const brigades = fireBrigades.map((fb: any) => ({
            id: fb.fireBrigadeId,
            type: 'Fire Brigade' as const,
            state: fb.state || 'UNKNOWN',
            sectorId: fb.sectorId || 0,
            agent: fb,
        }));

        const patrols = foresterPatrols.map((fp: any) => ({
            id: fp.foresterPatrolId,
            type: 'Forester Patrol' as const,
            state: fp.state || 'UNKNOWN',
            sectorId: fp.sectorId || 0,
            agent: fp,
        }));

        return [...brigades, ...patrols];
    }, [fireBrigades, foresterPatrols]);

    const handleRunRecommendation = useCallback((unitId: number, sectorId: number, agentType: 'Fire Brigade' | 'Forester Patrol') => {
        if (!sectorIds.has(sectorId)) {
            console.warn(`[ActorsDetailsTable] Sector ${sectorId} not found in configuration. Available: [${Array.from(sectorIds).join(', ')}]. Skipping.`);
            return;
        }
        const type = agentType === 'Fire Brigade' ? 'brigade' : 'forester';
        dispatch(sendBrigadeOrForesterMoveOrder(unitId, sectorId, type, 'manual'));
    }, [dispatch, sectorIds]);

    const getRecommendationForAgent = useCallback((agentId: number, agentType: 'Fire Brigade' | 'Forester Patrol') => {
        const typedKey = agentType === 'Fire Brigade'
            ? `fireBrigade:${agentId}`
            : `foresterPatrol:${agentId}`;

        const recommendation = recommendations[typedKey] || recommendations[String(agentId)];
        if (!recommendation || !recommendation.sectorId) {
            return null;
        }
        return recommendation;
    }, [recommendations]);

    const handleOpenMoveModal = useCallback((agentId: number, agentType: 'Fire Brigade' | 'Forester Patrol', currentSectorId: number) => {
        setSelectedAgent({ id: agentId, type: agentType, currentSectorId });
        setMoveModalOpen(true);
    }, []);

    const handleCloseMoveModal = useCallback(() => {
        setMoveModalOpen(false);
        setSelectedAgent(null);
    }, []);

    const handleMoveAgent = useCallback((targetSectorId: number) => {
        if (selectedAgent) {
            handleRunRecommendation(selectedAgent.id, targetSectorId, selectedAgent.type);
        }
    }, [selectedAgent, handleRunRecommendation]);

    return (
        <Box sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
            <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
                Agent Status
            </Typography>
            <TableContainer 
                component={Paper}
                sx={{ 
                    flex: 1,
                    minHeight: 0,
                    width: '100%',
                    overflowX: 'hidden',
                    overflowY: 'auto'
                }}
            >
                <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', width: '100%', '& td, & th': { px: 0.3, py: 0.75, fontSize: '0.7rem', textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }}>
                    <TableHead>
                        <TableRow>
                            <TableCell style={{ width: '10%' }}><strong>#</strong></TableCell>
                            <TableCell style={{ width: '12%' }}><strong>T</strong></TableCell>
                            <TableCell style={{ width: '22%' }}><strong>St</strong></TableCell>
                            <TableCell style={{ width: '12%' }}><strong>Sec</strong></TableCell>
                            <TableCell style={{ width: '18%' }}><strong>Rec</strong></TableCell>
                            <TableCell style={{ width: '13%' }}><strong>A</strong></TableCell>
                            <TableCell style={{ width: '13%' }}><strong>M</strong></TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {agents.map((agent) => {
                            const recommendation = getRecommendationForAgent(agent.id, agent.type);
                            // Use "EX->" for Forester Patrols, "MV->" for Fire Brigades
                            const recommendationPrefix = agent.type === 'Forester Patrol' ? 'EX->' : 'MV->';
                            const recommendationText = recommendation 
                                ? `${recommendationPrefix}${recommendation.sectorId}` 
                                : '';
                            const isSectorValid = recommendation?.sectorId ? sectorIds.has(Number(recommendation.sectorId)) : false;
                            
                            return (
                                <TableRow key={`${agent.type}-${agent.id}`}>
                                    <TableCell sx={{ textAlign: 'center' }}>{agent.id}</TableCell>
                                    <TableCell sx={{ textAlign: 'center' }}>
                                        <Chip 
                                            label={agent.type === 'Fire Brigade' ? 'FB' : 'FP'} 
                                            size="small"
                                            color={agent.type === 'Fire Brigade' ? 'error' : 'success'}
                                            sx={{ fontSize: '0.7rem', height: '20px' }}
                                        />
                                    </TableCell>
                                    <TableCell sx={{ textAlign: 'center' }}>{agent.state}</TableCell>
                                    <TableCell sx={{ textAlign: 'center' }}>{agent.sectorId > 0 ? agent.sectorId : '-'}</TableCell>
                                    <TableCell sx={{ textAlign: 'center' }}>
                                        {recommendationText || '-'}
                                    </TableCell>
                                    <TableCell sx={{ textAlign: 'center' }}>
                                        {recommendation && recommendation.sectorId && isSectorValid ? (
                                            <Button
                                                variant="contained"
                                                size="small"
                                                color="primary"
                                                onClick={() => handleRunRecommendation(
                                                    agent.id,
                                                    Number(recommendation.sectorId),
                                                    agent.type
                                                )}
                                                sx={{ fontSize: '0.7rem', py: 0.25, px: 1, minWidth: '60px' }}
                                            >
                                                Apply
                                            </Button>
                                        ) : (
                                            <span style={{ color: isSectorValid ? '#999' : '#c00' }}>
                                                {recommendation && recommendation.sectorId && !isSectorValid ? 'Invalid sector' : '-'}
                                            </span>
                                        )}
                                    </TableCell>
                                    <TableCell sx={{ textAlign: 'center' }}>
                                        <Button
                                            variant="outlined"
                                            size="small"
                                            onClick={() => handleOpenMoveModal(agent.id, agent.type, agent.sectorId)}
                                            sx={{ fontSize: '0.7rem', py: 0.25, px: 1, minWidth: '60px' }}
                                        >
                                            Move
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            </TableContainer>
            {selectedAgent && (
                <MoveAgentModal
                    isOpen={moveModalOpen}
                    onClose={handleCloseMoveModal}
                    onMove={handleMoveAgent}
                    agentId={selectedAgent.id}
                    agentType={selectedAgent.type}
                    currentSectorId={selectedAgent.currentSectorId}
                />
            )}
        </Box>
    );
}
