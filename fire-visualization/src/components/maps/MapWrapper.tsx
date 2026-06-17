import { ReactNode } from 'react';

type MapWrapperProps = {
  children: ReactNode;
};

// MapLibre doesn't need API provider - just pass through children
export const MapWrapper = ({ children }: MapWrapperProps) => {
  return <>{children}</>;
};
