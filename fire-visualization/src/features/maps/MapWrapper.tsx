import { ReactNode } from 'react';
import { ErrorBoundary } from '../../components/ErrorBoundary';

type MapWrapperProps = {
  children: ReactNode;
};

// MapLibre doesn't need API provider
export const MapWrapper = ({ children }: MapWrapperProps) => {
  return <ErrorBoundary>{children}</ErrorBoundary>;
};
