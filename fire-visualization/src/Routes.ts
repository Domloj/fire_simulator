import { useRoutes } from 'react-router-dom';
import { MainRoutes } from './routes/MainRoutes';

export const Routes = () => {
  return useRoutes([MainRoutes]);
};
