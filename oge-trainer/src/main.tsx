import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { createApi, SetupError } from './lib/api';
import SetupScreen from './pages/SetupScreen';
import './styles.css';

const root = createRoot(document.getElementById('root')!);
createApi()
  .then((api) => root.render(<StrictMode><App api={api} /></StrictMode>))
  .catch((e) => root.render(<SetupScreen message={e instanceof SetupError ? e.message : String(e)} />));
