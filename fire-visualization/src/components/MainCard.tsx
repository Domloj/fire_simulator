import { HTMLProps, ReactNode, forwardRef } from 'react';

// material-ui
import { useTheme } from '@mui/material/styles';
import { Card, CardContent, CardHeader, Divider, Typography } from '@mui/material';

// project import
import { Highlighter } from './Highlighter';
import '../assets/styles/MainCard.css';

// ==============================|| CUSTOM - MAIN CARD ||============================== //

type MainCardProps = Partial<{
  hasBorder: boolean;
  hasBoxShadow: boolean;
  hasDarkTitle: boolean;
  hasDivider: boolean;
  hasContent: boolean;
  contentSX: object;
  elevation: number;
  secondary: ReactNode;
  shadow: string;
  sx: object;
  title: ReactNode | string; // TODO doesn't work
  codeHighlight: boolean;
  children: ReactNode;
}>;

export const MainCard = forwardRef<HTMLDivElement, HTMLProps<HTMLDivElement> & MainCardProps>(
  (
    {
      hasBorder = true,
      hasBoxShadow,
      hasDarkTitle,
      hasContent = true,
      contentSX = {},
      sx = {},
      elevation,
      secondary,
      shadow,
      title,
      codeHighlight,
      children,
      ...others
    }: MainCardProps,
    ref,
  ) => {
    const theme = useTheme();
    hasBoxShadow = theme.palette.mode === 'dark' ? hasBoxShadow || true : hasBoxShadow;

    return (
      <Card
        elevation={elevation ?? 0}
        className="main-card"
        ref={ref}
        {...others}
        sx={{
          border: hasBorder ? '1px solid' : 'none',
          borderColor: theme.palette.mode === 'dark' ? theme.palette.divider : theme.palette.grey['800'],
          boxShadow:
            hasBoxShadow && (!hasBorder || theme.palette.mode === 'dark')
              ? shadow ?? theme.customShadows?.z1 ?? 'inherit'
              : 'inherit',
          ':hover': {
            boxShadow: hasBoxShadow ? shadow ?? theme.customShadows?.z1 ?? 'inherit' : 'inherit',
          },
          '& pre': {
            fontFamily: theme.typography.fontFamily,
          },
          ...sx,
        }}
      >
        {/* card header and action */}
        {!hasDarkTitle && title && (
          <CardHeader
            className="main-card-header"
            titleTypographyProps={{ variant: 'subtitle1' }}
            title={title}
            action={secondary}
          />
        )}
        {hasDarkTitle && title && (
          <CardHeader
            className="main-card-header"
            title={<Typography variant="h3">{title}</Typography>}
            action={secondary}
          />
        )}

        {/* card content */}
        {hasContent && <CardContent className="main-card-content" sx={contentSX}>{children}</CardContent>}
        {!hasContent && children}

        {/* card footer - clipboard & highlighter  */}
        {codeHighlight && (
          <>
            <Divider sx={{ borderStyle: 'dashed' }} />
            <div className="main-card-highlighter">
              <Highlighter>{children}</Highlighter>
            </div>
          </>
        )}
      </Card>
    );
  },
);
MainCard.displayName = 'MainCard';
