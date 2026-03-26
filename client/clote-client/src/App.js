import { AuthProvider, useAuth } from "./AuthContext";
import { ToastProvider } from "./ToastContext";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import "./index.css";

function AppInner() {
    const { isAuthed } = useAuth();
    return isAuthed ? < Dashboard / > : < AuthPage / > ;
}

export default function App() {
    return ( <
        ToastProvider >
        <
        AuthProvider >
        <
        AppInner / >
        <
        /AuthProvider> <
        /ToastProvider>
    );
}