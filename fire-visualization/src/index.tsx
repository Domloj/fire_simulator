// Disable console logging
if (process.env.NODE_ENV === 'production' || true) {
  console.log = () => {};
  console.warn = () => {};
  console.error = () => {};
  console.info = () => {};
  console.debug = () => {};
}

import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { Provider as ReduxProvider } from 'react-redux';
import { reduxStore } from './store/reduxStore';
import { ScrollTop } from './components/ScrollTop';
import { ThemeCustomization } from './themes/ThemeCustomization';
import { Routes } from './Routes';
import Footer from './components/Footer';
import "./index-overrides.css";

const App = () => {
  return (
    <ThemeCustomization>
      <ScrollTop>
        <Routes />
        <Footer />
      </ScrollTop>
    </ThemeCustomization>
  );
};

const root = createRoot(document.getElementById('root')!);

window.addEventListener('error', (ev) => {
  // window.__LAST_ERROR__ = { error: ev.error, message: ev.message, stack: ev.error?.stack };
});

window.addEventListener('unhandledrejection', (ev) => {
  // window.__LAST_REJECTION__ = { reason: ev.reason, stack: ev.reason?.stack };
});

root.render(
  /*
   * Had do disable React.StrictMode due to
   * google-maps with deck.gl overlays not working and giving null errors
   */
  // <StrictMode>
  <ReduxProvider store={reduxStore}>
    <HashRouter>
      <App />
    </HashRouter>
  </ReduxProvider>,
  // </StrictMode>,
);
