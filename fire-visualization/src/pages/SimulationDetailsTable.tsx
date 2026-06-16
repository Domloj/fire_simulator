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
    TableContainer
} from '@mui/material';
import { RootState } from '../store/reduxStore';
import { useMemo } from 'react';

export default function SimulationDetailsTable() {
    const mapConfigState = useSelector((state: RootState) => state.mapConfiguration);

    const {
        configuration: mapConfiguration,
    } = mapConfigState || {};

    const sectors = mapConfiguration?.sectors || [];

    return (
        <Box sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
            <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
                Sector Fire Status
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
                <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', width: '100%', '& td, & th': { px: 0.5, py: 0.75, fontSize: '0.75rem', textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }}>
                    <TableHead>
                        <TableRow>
                            <TableCell style={{ width: '20%' }}><strong>ID</strong></TableCell>
                            <TableCell style={{ width: '26%' }}><strong>Fire</strong></TableCell>
                            <TableCell style={{ width: '26%' }}><strong>Burn</strong></TableCell>
                            <TableCell style={{ width: '28%' }}><strong>Ext</strong></TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {sectors.map((sector, index) => (
                            <TableRow key={sector?.sectorId || `sector-${index}`}>
                                <TableCell sx={{ textAlign: 'center' }}>{sector?.sectorId ?? 'N/A'}</TableCell>
                                <TableCell sx={{ textAlign: 'center' }}>
                                    {sector?.fireLevel !== null && sector?.fireLevel !== undefined
                                        ? sector.fireLevel.toFixed(2)
                                        : '0.00'}
                                </TableCell>
                                <TableCell sx={{ textAlign: 'center' }}>
                                    {sector?.burnLevel !== null && sector?.burnLevel !== undefined
                                        ? sector.burnLevel.toFixed(2)
                                        : '0.00'}
                                </TableCell>
                                <TableCell sx={{ textAlign: 'center' }}>
                                    {sector?.extinguishLevel !== null && sector?.extinguishLevel !== undefined
                                        ? sector.extinguishLevel.toFixed(2)
                                        : '0.00'}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Box>
    );
}
