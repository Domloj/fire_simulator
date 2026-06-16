import { AppLayout } from '../layout/AppLayout';
import { MainPage } from '../pages/MainPage';
import { SimulationPage } from '../pages/SimulationPage';
import { SettingsPage } from '../pages/SettingsPage';

// ==============================|| MAIN ROUTING ||============================== //

export const MainRoutes = {
  path: '/',
  element: <AppLayout />,
  children: [
    {
      path: '/',
      element: <MainPage />,
    },
    {
      path: '/settings/:settingId?',
      element: <SettingsPage />,
    },
    {
      path: '/simulation',
      element: <SimulationPage />,
    },
  ],
};
