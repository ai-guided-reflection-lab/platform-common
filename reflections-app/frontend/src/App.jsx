import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Chat from './Chat';
import ProfessorConfig from './ProfessorConfig';
import Dashboard from './Dashboard';
import RecSys from './RecSys';

export default function App() {
    return (
        <BrowserRouter>
            <div className="app">
                <nav>
                    <span className="logo">Reflection Chatbot</span>
                    <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>
                        Chat
                    </NavLink>
                    <NavLink to="/config" className={({ isActive }) => isActive ? 'active' : ''}>
                        Professor Config
                    </NavLink>
                    <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'active' : ''}>
                        Dashboard
                    </NavLink>
                    <NavLink to="/scs" className={({ isActive }) => isActive ? 'active' : ''}>
                        SCS
                    </NavLink>
                    <NavLink to="/llm-scs" className={({ isActive }) => isActive ? 'active' : ''}>
                        LLM-SCS
                    </NavLink>
                </nav>

                <Routes>
                    <Route path="/" element={<Chat />} />
                    <Route path="/config" element={<ProfessorConfig />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/scs" element={<RecSys mode="scs" />} />
                    <Route path="/llm-scs" element={<RecSys mode="llm-scs" />} />
                </Routes>
            </div>
        </BrowserRouter>
    );
}
