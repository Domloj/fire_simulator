import PropTypes from 'prop-types';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Button, Stack, Typography, useTheme } from '@mui/material';
import { LogEntry } from '../../store/logsSlice';

/**
 * So, this is the LogTerminal component.
 * It provides a terminal-like interface for viewing log entries.
 * 
 * The component uses React hooks for state management and Redux for global state access.
 * @returns 
 */

type Props = {
  title: string;
  entries: LogEntry[];
  onClear: () => void;
};

export const LogTerminal: React.FC<Props> = ({ title, entries, onClear }) => {
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const theme = useTheme();

  const formatted = useMemo(
    () =>
      entries.map((entry) => {
        const time = new Date(entry.timestamp).toLocaleTimeString();
        return {
          time,
          level: entry.level ? entry.level.toUpperCase() : '',
          text: entry.text,
        };
      }),
    [entries],
  );

  useEffect(() => {
    if (!autoScroll) return;
    const el = containerRef.current;
    if (el) {
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [entries.length, autoScroll]); 

  return (
    <Box 
      className="log-terminal-container" 
      sx={{ 
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        display: 'flex', 
        flexDirection: 'column',
        overflow: 'hidden'
      }}
    >
      <Stack 
        direction="row" 
        alignItems="center" 
        spacing={1} 
        justifyContent="space-between" 
        className="log-terminal-header"
        sx={{ flexShrink: 0 }}
      >
        <Typography variant="subtitle2">{title}</Typography>
        <Stack direction="row" alignItems="center" spacing={1} className="log-terminal-actions">
          <Button
            size="small"
            variant={autoScroll ? 'contained' : 'outlined'}
            onClick={() => setAutoScroll((v) => !v)}
          >
            Auto-scroll {autoScroll ? 'On' : 'Off'}
          </Button>
          <Button size="small" variant="outlined" onClick={onClear}>
            Clear
          </Button>
        </Stack>
      </Stack>
      <Box
        ref={containerRef}
        className="log-terminal-content"
        sx={{
          bgcolor: theme.palette.background.paper,
          color: theme.palette.text.primary,
          borderColor: `rgba(0, 0, 0, 0.12)`,
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {formatted.length === 0 ? (
          <Typography variant="caption" className="log-terminal-empty">
            No entries
          </Typography>
        ) : (
          formatted.map((line, idx) => (
            <div
              key={idx}
              style={{
                padding: '1px 4px',
                display: 'flex',
                gap: 8,
                alignItems: 'flex-start',
                fontFamily: 'Monaco, Menlo, "Courier New", monospace',
                fontSize: 12,
                lineHeight: '1.2',
                whiteSpace: 'pre-wrap',
              }}
            >
              <span style={{ color: theme.palette.text.secondary, minWidth: 92 }}>{`[${line.time}]`}</span>
              {line.level ? (
                <span
                  style={{
                    color: ((): string => {
                      switch (line.level) {
                        case 'ERROR':
                          return theme.palette.error.main;
                        case 'WARN':
                        case 'WARNING':
                          return theme.palette.warning.dark || '#FFA000';
                        case 'DEBUG':
                          return theme.palette.text.secondary;
                        default:
                          return theme.palette.info.main || '#2196F3';
                      }
                    })(),
                    fontWeight: 700,
                    minWidth: 56,
                  }}
                >
                  {line.level}
                </span>
              ) : (
                <span style={{ minWidth: 56 }} />
              )}
              <span style={{ color: theme.palette.text.primary, flex: 1 }}>{line.text}</span>
            </div>
          ))
        )}
      </Box>
    </Box>
  );
};

LogTerminal.propTypes = {
  title: PropTypes.string.isRequired,
  entries: PropTypes.arrayOf(
    PropTypes.shape({
      timestamp: PropTypes.number.isRequired,
      level: PropTypes.string,
      text: PropTypes.string.isRequired,
    })
  ).isRequired,
  onClear: PropTypes.func.isRequired,
};


export default LogTerminal;
